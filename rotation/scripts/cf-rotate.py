#!/usr/bin/env python3
"""Rotate Cloudflare DNS token. Needs CF_GLOBAL_KEY + CF_EMAIL from K8s secret."""
import base64, json, os, secrets, subprocess, sys, time, urllib.request

def sh(cmd, timeout=30):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or r.stderr).strip()

def kub(cmd):
    return sh("kubectl " + cmd)

def cf(method, path, token, body=None):
    url = "https://api.cloudflare.com/client/v4" + path
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def cf_global(method, path, gkey, gemail, body=None):
    url = "https://api.cloudflare.com/client/v4" + path
    h = {"X-Auth-Email": gemail, "X-Auth-Key": gkey, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

if __name__ == "__main__":
    print("=== CF Token Rotation ===")

    # Read current token from K8s
    rc, b64 = kub("get secret -n cert-manager cloudflare-secrets -o jsonpath={{.data.cloudflare-token}}")
    if rc != 0 or not b64:
        print("FAIL: no token in cert-manager"); sys.exit(1)
    cur = base64.b64decode(b64).decode()

    # Verify current token
    r = cf("GET", "/user/tokens/verify", cur)
    if r.get("success"):
        exp = r["result"].get("expires_on", "never")
        print("Current: valid, expires " + exp)
    else:
        print("Current: INVALID - " + r.get("errors", [{}])[0].get("message", "?"))

    # Read Global Key from K8s secret (rotation-global-key in rotation ns)
    rc_gk, gk_b64 = kub("get secret -n rotation rotation-global-key -o jsonpath={{.data.cf_global_key}}")
    rc_ge, ge_b64 = kub("get secret -n rotation rotation-global-key -o jsonpath={{.data.cf_email}}")
    if rc_gk != 0 or rc_ge != 0:
        print("SKIP: set rotation-global-key secret with cf_global_key + cf_email")
        sys.exit(0)

    gkey = base64.b64decode(gk_b64).decode().strip()
    gemail = base64.b64decode(ge_b64).decode().strip()

    # Create new token
    ts = time.strftime("%Y%m%d-%H%M%S")
    body = {
        "name": "lag0-dns-" + ts,
        "policies": [{
            "effect": "allow",
            "resources": {"com.cloudflare.api.account.zone.*": "*"},
            "permission_groups": [
                {"id": "c8fed203ed3043cba015a93ad1616f1f"},
                {"id": "82e64a83756745bbbb1c9c2701bf816b"},
            ],
        }],
    }
    r = cf_global("POST", "/user/tokens", gkey, gemail, body)
    if not r.get("success"):
        print("FAIL create: " + r.get("errors", [{}])[0].get("message", "?"))
        sys.exit(1)

    nt = r["result"]["value"]
    print("New token created: " + body["name"])

    # TEST before replace
    time.sleep(3)
    t = cf("GET", "/user/tokens/verify", nt)
    if not t.get("success"):
        print("FAIL verify - old token preserved"); sys.exit(1)
    print("New token VERIFIED")

    # Replace
    nb = base64.b64encode(nt.encode()).decode()
    kub("patch secret -n cert-manager cloudflare-secrets -p '{\"data\":{\"cloudflare-token\":\"" + nb + "\"}}'")
    print("cert-manager secret updated")
    kub("rollout restart deployment -n cert-manager cert-manager 2>/dev/null || true")
    print("cert-manager restarted")

    # Cleanup old tokens
    old = cf_global("GET", "/user/tokens", gkey, gemail)
    if old.get("success"):
        for t in old.get("result", []):
            if t.get("status") == "active" and t.get("name", "").startswith("lag0-dns-") \
               and t["name"] != body["name"]:
                cf_global("DELETE", "/user/tokens/" + t["id"], gkey, gemail)
                print("Deleted old: " + t["name"])

    print("OK rotation complete")
    sys.exit(0)
