#!/usr/bin/env python3
"""Rotate the Cloudflare Tunnel credential used by the `nb-mgmt` tunnel and update the
Kubernetes Secret consumed by the cloudflared Deployment in ton-cluster.

WHY: `cloudflare-tunnel/credentials-secret.yaml` was committed to a PUBLIC repository, so the
TunnelSecret (and the token form of it) must be treated as compromised. Deleting the file does
not remove it from git history — only rotation neutralizes it. See cloudflare-tunnel/SECRETS.md.

Requires a Cloudflare API token with:
    Cloudflare Tunnel Write   (Account scope)   -> PATCH /cfd_tunnel/{id}
    Cloudflare One Connectors Write             -> optional, only for --force-disconnect

Environment (all optional except the token):
    CF_API_TOKEN        Cloudflare API token (or use CF_API_TOKEN_FILE)
    CF_API_TOKEN_FILE   file containing the token
    CF_ACCOUNT_ID       default c1cc5014eef16759e267a5d4f8254d4d
    TUNNEL_ID           default 6f50e834-7f17-4cc4-82ff-29ce2c3f5cf5 (nb-mgmt)
    K8S_NAMESPACE       default cloudflare-tunnel
    K8S_SECRET          default cloudflared-credentials
    K8S_SECRET_KEY      default credentials.json
    K8S_DEPLOYMENT      default cloudflared
    SA_DIR              default /var/run/secrets/kubernetes.io/serviceaccount
    K8S_API             default https://kubernetes.default.svc

Usage:
    python3 cf-tunnel-rotate.py --check              # permissions + current state, changes nothing
    python3 cf-tunnel-rotate.py --dry-run            # print the steps, change nothing
    python3 cf-tunnel-rotate.py --rotate-only        # rotate in Cloudflare, leave K8s alone
    python3 cf-tunnel-rotate.py --force-disconnect   # rotate + K8s Secret + restart + kill old conns

Notes:
  * stdlib only: no kubectl, no curl, no jq. Runs on python:3-alpine with a ServiceAccount that
    can patch Secrets and Deployments in the target namespace. (The `rotation-cf` CronJob image
    `python:3-alpine` has no kubectl while its script shells out to it — that is why it fails.)
  * Never prints the credential. Verify with the sha256 it reports.
  * After running, store the new value in Vaultwarden; the K8s Secret is the only copy otherwise.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.request

CF_API = "https://api.cloudflare.com/client/v4"


def env(name, default=None):
    value = os.environ.get(name) or default
    if value is None:
        log("FATAL: %s is not set" % name)
        sys.exit(2)
    return value


def log(msg):
    print(msg, flush=True)


def http(method, url, headers, body=None, context=None, timeout=25):
    """Returns (status_code, parsed_json_or_None, raw_text)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        status = exc.code
    except Exception as exc:  # noqa: BLE001 - network/TLS failures are reported as-is
        return 0, None, "transport error: %s" % exc
    try:
        return status, json.loads(raw), raw
    except ValueError:
        return status, None, raw


def cf_token():
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not token:
        token_file = os.environ.get("CF_API_TOKEN_FILE", "")
        if token_file and os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8") as handle:
                token = handle.read().strip()
    if not token:
        log("FATAL: no Cloudflare API token (CF_API_TOKEN or CF_API_TOKEN_FILE)")
        sys.exit(2)
    return token


def cf(method, path, token, body=None):
    return http(
        method,
        CF_API + path,
        {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        body,
    )


def k8s(method, path, body=None):
    sa_dir = env("SA_DIR", "/var/run/secrets/kubernetes.io/serviceaccount")
    if not os.path.exists(os.path.join(sa_dir, "token")):
        log("FATAL: no ServiceAccount token at %s (are you running in-cluster?)" % sa_dir)
        sys.exit(2)
    with open(os.path.join(sa_dir, "token"), "r", encoding="utf-8") as handle:
        token = handle.read().strip()
    context = ssl.create_default_context(cafile=os.path.join(sa_dir, "ca.crt"))
    return http(
        method,
        env("K8S_API", "https://kubernetes.default.svc") + path,
        {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/merge-patch+json",
            "Accept": "application/json",
        },
        body,
        context,
    )


def cf_errors(payload):
    if not payload:
        return "no JSON body"
    codes = payload.get("errors") or []
    return "; ".join("%s %s" % (item.get("code"), item.get("message")) for item in codes) or "none"


def main():
    parser = argparse.ArgumentParser(description="Rotate the nb-mgmt Cloudflare Tunnel secret")
    parser.add_argument("--check", action="store_true", help="verify permissions, change nothing")
    parser.add_argument("--dry-run", action="store_true", help="print steps, change nothing")
    parser.add_argument("--rotate-only", action="store_true", help="do not touch Kubernetes")
    parser.add_argument("--force-disconnect", action="store_true",
                        help="delete existing tunnel connections (recommended for a leaked secret)")
    args = parser.parse_args()

    account_id = env("CF_ACCOUNT_ID", "c1cc5014eef16759e267a5d4f8254d4d")
    tunnel_id = env("TUNNEL_ID", "6f50e834-7f17-4cc4-82ff-29ce2c3f5cf5")
    namespace = env("K8S_NAMESPACE", "cloudflare-tunnel")
    secret_name = env("K8S_SECRET", "cloudflared-credentials")
    secret_key = env("K8S_SECRET_KEY", "credentials.json")
    deployment = env("K8S_DEPLOYMENT", "cloudflared")
    tunnel_path = "/accounts/%s/cfd_tunnel/%s" % (account_id, tunnel_id)
    token = cf_token()

    log("=== Cloudflare Tunnel rotation (nb-mgmt) ===")

    status, payload, raw = cf("GET", tunnel_path, token)
    if not payload or not payload.get("success"):
        log("FAIL: cannot read the tunnel (HTTP %s): %s" % (status, cf_errors(payload)))
        log("      the token needs 'Cloudflare One Connectors Read' / 'Cloudflare Tunnel Read'")
        sys.exit(1)
    tunnel = payload["result"]
    log("tunnel: name=%s config_src=%s status=%s" %
        (tunnel.get("name"), tunnel.get("config_src"), tunnel.get("status")))

    if tunnel.get("config_src") != "local":
        log("NOTE: this tunnel is remotely configured (config_src=%s); its credential is the "
            "token from the dashboard, and PATCH tunnel_secret still applies." % tunnel.get("config_src"))

    if args.check:
        # A no-op PATCH (same name, no secret) proves write permission without rotating anything.
        status, payload, raw = cf("PATCH", tunnel_path, token, {"name": tunnel.get("name")})
        if payload and payload.get("success"):
            log("OK: token has read + write on this tunnel; nothing was changed.")
            sys.exit(0)
        log("FAIL: token can read but NOT write the tunnel (HTTP %s): %s" % (status, cf_errors(payload)))
        log("      needs 'Cloudflare Tunnel Write' (Account scope)")
        sys.exit(1)

    new_secret = base64.b64encode(secrets.token_bytes(32)).decode()
    credentials = json.dumps({
        "AccountTag": account_id,
        "TunnelID": tunnel_id,
        "TunnelSecret": new_secret,
    }, separators=(",", ":"))
    credentials_b64 = base64.b64encode(credentials.encode()).decode()
    digest = hashlib.sha256(credentials_b64.encode()).hexdigest()[:16]

    if args.dry_run:
        log("[dry-run] would PATCH %s with a fresh 32-byte tunnel_secret" % tunnel_path)
        log("[dry-run] would write %s/%s key %s (sha256[0:16]=%s)"
            % (namespace, secret_name, secret_key, digest))
        if args.force_disconnect:
            log("[dry-run] would DELETE %s/connections" % tunnel_path)
        log("[dry-run] would restart deployment %s/%s" % (namespace, deployment))
        sys.exit(0)

    log("rotating secret ...")
    status, payload, raw = cf("PATCH", tunnel_path, token, {"tunnel_secret": new_secret})
    if not payload or not payload.get("success"):
        log("FAIL: rotation rejected (HTTP %s): %s" % (status, cf_errors(payload)))
        sys.exit(1)
    log("OK: Cloudflare accepted the new tunnel secret (old one can no longer open connections)")

    if args.rotate_only:
        log("rotate-only: Kubernetes untouched. The cloudflared replicas still hold the OLD secret "
            "and keep working until they restart — an attacker's connector would too.")
        sys.exit(0)

    log("updating Secret %s/%s ..." % (namespace, secret_name))
    status, payload, raw = k8s(
        "PATCH",
        "/api/v1/namespaces/%s/secrets/%s" % (namespace, secret_name),
        {"data": {secret_key: credentials_b64}},
    )
    if status not in (200, 201) or (payload and payload.get("kind") == "Status"):
        log("FAIL: could not patch the Secret (HTTP %s): %s" % (status, raw[:300]))
        log("      the ServiceAccount needs 'patch' on secrets in namespace %s" % namespace)
        sys.exit(1)
    log("OK: Secret updated (sha256[0:16]=%s) — compare with:" % digest)
    log("    kubectl get secret -n %s %s -o jsonpath='{.data.%s}' | base64 -d | base64 | tr -d '\\n' | sha256sum"
        % (namespace, secret_name, secret_key.replace(".", "\\.")))

    if args.force_disconnect:
        log("forcing disconnect of existing tunnel connections ...")
        status, payload, raw = cf("DELETE", tunnel_path + "/connections", token)
        if payload and payload.get("success"):
            log("OK: existing connections dropped (the attacker's replica lost its connection too)")
        else:
            log("WARN: could not drop connections (HTTP %s): %s" % (status, cf_errors(payload)))
            log("      needs 'Cloudflare One Connectors Write'")

    log("restarting deployment %s/%s ..." % (namespace, deployment))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status, payload, raw = k8s(
        "PATCH",
        "/apis/apps/v1/namespaces/%s/deployments/%s" % (namespace, deployment),
        {"spec": {"template": {"metadata": {"annotations":
            {"kubectl.kubernetes.io/restartedAt": stamp}}}}},
    )
    if status not in (200, 201) or (payload and payload.get("kind") == "Status"):
        log("FAIL: could not restart the deployment (HTTP %s): %s" % (status, raw[:300]))
        log("      restart it by hand: kubectl rollout restart -n %s deploy/%s" % (namespace, deployment))
        sys.exit(1)
    log("OK: rollout requested — cloudflared will reconnect with the new credential")
    log("verify with: kubectl logs -n %s deploy/%s | grep 'Registered tunnel connection'" % (namespace, deployment))

    log("")
    log("NOW: paste the new credential into Vaultwarden (and delete the old item/revision).")
    log("     It is the only durable copy — the K8s Secret is not in git (repo is public).")


if __name__ == "__main__":
    main()
