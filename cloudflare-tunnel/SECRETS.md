# cloudflare-tunnel — credentials

The `cloudflared` Deployment runs the **locally-managed** tunnel `nb-mgmt`
(`6f50e834-7f17-4cc4-82ff-29ce2c3f5cf5`, account `c1cc5014eef16759e267a5d4f8254d4d`) and mounts
its credential from the Secret **`cloudflare-tunnel/cloudflared-credentials`**, key
`credentials.json`.

## ⚠️ Why `credentials-secret.yaml` is gone

That file was committed here, and **this repository is public** — anyone could read the
`TunnelSecret` and register their own connector on the tunnel (which would let them serve
traffic for `*.lag0.com.br`). The file was removed from the tree on **2026-09-18** and the
credential must be **rotated**: deleting a file does not delete it from git history, so only
rotation neutralizes a leaked secret.

After rotation the credential lives **only** in the cluster (the Kustomization runs with
`prune: false`, so removing the resource from git leaves the Secret in place) and must be
backed up in Vaultwarden. Nothing in this directory may ever contain the value again.

## Read the credential that is live in the cluster

```bash
kubectl get secret -n cloudflare-tunnel cloudflared-credentials \
  -o jsonpath='{.data.credentials\.json}' | base64 -d
```

## Rotate it

Both paths must be followed by updating the Secret and restarting `cloudflared`: replicas keep
the credential they started with, and an attacker's replica does too (Cloudflare only refuses
*new* connections opened with the old secret).

### A. Automated (API) — `rotation/scripts/cf-tunnel-rotate.py`

Needs a Cloudflare API token with **`Cloudflare Tunnel Write`** (Account scope); recommended
home for that token is a Vaultwarden item synced by VKS into the `rotation` namespace.

```bash
# 1. permissions + current state (changes nothing)
python3 rotation/scripts/cf-tunnel-rotate.py --check

# 2. rotate: PATCH cfd_tunnel {tunnel_secret}, update the K8s Secret, restart cloudflared,
#    drop existing connections (what Cloudflare recommends for a compromised token)
python3 rotation/scripts/cf-tunnel-rotate.py --force-disconnect
```

`--force-disconnect` calls `DELETE /cfd_tunnel/{id}/connections`, which kills any connector
holding the old secret, including an attacker's. Expect a few seconds of downtime for
`*.lag0.com.br`. The script is stdlib-only (no `kubectl`, no `curl`) so it runs on
`python:3-alpine` with a ServiceAccount that can patch Secrets and Deployments — unlike
`cf-rotate.py`, which shells out to `kubectl` from that same image.

### B. Manual (dashboard)

1. Cloudflare dashboard → **Networking → Tunnels → nb-mgmt → Rotate token**.
2. Store the new token in Vaultwarden — never in git.
3. Put it back into the Secret (`eyJ...` is base64 of `{"a":account,"t":tunnel,"s":secret}`)
   and restart:

   ```bash
   kubectl rollout restart -n cloudflare-tunnel deploy/cloudflared
   ```

## Related

* `../rotation/scripts/cf-tunnel-rotate.py` — rotation tool (untested against a live token:
  no credential in this cluster has `Cloudflare Tunnel Write`, see the note above).
* `../rotation/scripts/cf-rotate.py` — rotates the *DNS* API token
  (`cert-manager/cloudflare-secrets`). Its CronJob runs on `python:3-alpine`, which has **no
  `kubectl`** while the script shells out to it → every run exits 1
  (`BackoffLimitExceeded`, last run 2026-09-01). It also needs the missing
  `rotation/rotation-global-key` secret.
* Keep this directory free of any `credentials.json`, token or key.
