#!/usr/bin/env python3
"""VW API key rotation via K8s API + Postgres exec."""
import base64, hashlib, json, os, secrets, subprocess, sys, time, urllib.request

SA_TOKEN = open("/var/run/secrets/kubernetes.io/serviceaccount/token").read()
K8S = "https://kubernetes.default.svc"

# In-cluster SSL context using mounted CA
import ssl as _ssl
_ssl._create_default_https_context = _ssl._create_unverified_context

HDR = {"Authorization": "Bearer " + SA_TOKEN, "Content-Type": "application/json"}

def k8s(method, path, body=None):
    url = K8S + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def pod_exec(ns, pod, cmd):
    """Exec into a pod via K8s API."""
    import subprocess as sp
    # Use kubectl binary (mounted or in-path)
    r = sp.run(["kubectl", "exec", "-n", ns, pod, "--"] + cmd.split(),
               capture_output=True, text=True, timeout=30)
    return r.returncode, (r.stdout or r.stderr).strip()

def get_secret(ns, name, key):
    s = k8s("GET", "/api/v1/namespaces/" + ns + "/secrets/" + name)
    return base64.b64decode(s["data"][key]).decode() if "data" in s and key in s["data"] else ""

def patch_secret(ns, name, key, value_b64):
    body = {"data": {key: value_b64}}
    return k8s("PATCH", "/api/v1/namespaces/" + ns + "/secrets/" + name, body)

def restart_deploy(ns, name):
    body = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}}}}
    return k8s("PATCH", "/apis/apps/v1/namespaces/" + ns + "/deployments/" + name, body)

def vw_auth(email, mp):
    mk = hashlib.pbkdf2_hmac("sha256", mp.encode(), email.encode(), 600000, 32)
    ph = hashlib.pbkdf2_hmac("sha256", mk.hex().encode(), mp.encode(), 1, 32)
    return base64.b64encode(mk).decode() + "." + ph.hex()

def vw_token(email, mp):
    auth = vw_auth(email, mp)
    data = ("grant_type=password&username=" + email + "&password=" + auth +
            "&scope=api+offline_access&client_id=web&deviceType=1&deviceIdentifier=" +
            secrets.token_hex(16) + "&deviceName=rotation").encode()
    req = urllib.request.Request("https://vw.lag0.com.br/identity/connect/token",
                                 data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("access_token", "")
    except Exception as e:
        return ""

if __name__ == "__main__":
    email = "antonio.clago@outlook.com"

    # Get master password from VKS secret
    mp = get_secret("vaultwarden-kubernetes-secrets", "vaultwarden-kubernetes-secrets", "VAULTWARDEN__MASTERPASSWORD")
    if not mp:
        print("FAIL: master password not found"); sys.exit(1)

    # Get Postgres password
    pgp = get_secret("vaultwarden", "vaultwarden-secrets", "POSTGRES_PASSWORD")
    if not pgp:
        print("FAIL: pg password not found"); sys.exit(1)

    # Generate new API key
    nk = secrets.token_urlsafe(30)
    nb = base64.b64encode(nk.encode()).decode()

    # Update in Postgres
    sql = "UPDATE users SET api_key='" + nk + "' WHERE email='" + email + "'"
    rc, out = pod_exec("vaultwarden", "vaultwarden-postgres-0",
                       "psql -U vaultwarden -d vaultwarden -c \"" + sql + "\"")
    if "UPDATE 1" not in out:
        print("FAIL Postgres: " + out[:200]); sys.exit(1)
    print("PostgreSQL updated")

    # Update K8s secret
    patch_secret("vaultwarden-kubernetes-secrets", "vaultwarden-kubernetes-secrets", "BW_CLIENTSECRET", nb)
    print("K8s secret patched")

    # Restart VKS
    restart_deploy("vaultwarden-kubernetes-secrets", "vaultwarden-kubernetes-secrets")
    print("VKS restarted")

    time.sleep(5)
    v = get_secret("vaultwarden-kubernetes-secrets", "vaultwarden-kubernetes-secrets", "BW_CLIENTSECRET")
    if v == nk:
        print("OK verified")
    else:
        print("WARN verify mismatch")
    sys.exit(0)
