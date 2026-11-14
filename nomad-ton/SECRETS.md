# Secrets — nomad

`lag0-fleet-manifests` is a **public** repository: nothing in this directory holds a live value.

Vaultwarden organization `kubernetes-secrets`, item **`nomad-ton`** (Secure Note). Custom fields:

| Field | Type | Content |
|---|---|---|
| `acl_bootstrap_token` | Hidden | output of `nomad acl bootstrap` (management token) |
| `oidc_client_secret` | Hidden | Pocket ID client `nomad` secret (rotate with `POST /api/oidc/clients/<id>/secrets`) |
| `namespaces` | Text | `nomad` |

Kubernetes Secrets consumed by the workload:

| Secret | Keys | Used by |
|---|---|---|
| `nomad-acl` | `token` | operator CLI / UI (management token) |
| `nomad-oidc` | `OIDC_CLIENT_SECRET` | re-creating the OIDC auth method (stored in raft, not read by the agent at boot) |

Both were created with `kubectl create secret` in namespace `nomad` (outside Flux) because
Vaultwarden Kubernetes Secrets cannot be seeded by the agent. They are not referenced by the
manifests, so nothing breaks if they are missing — but keep the Vaultwarden item in sync, otherwise
a rebuilt cluster cannot be re-authenticated.

Rotation:

```bash
# OIDC client secret (Pocket ID generates it; the old one is revoked by deleting its entry)
curl -s -b /tmp/pid.txt -X POST https://id.lag0.com.br/api/oidc/clients/9d992eb9-3fd9-4c58-9eaf-dbd4fd20f059/secrets
# then update the auth method:
#   nomad acl auth-method create ... -config @oidc.json  (with the new secret)
# and update Vaultwarden + the nomad-oidc Secret

# ACL bootstrap/management token: create a new management token, store it, delete the old
nomad acl token create -name=admin-$(date +%F) -policy=nomad-admin   # or -type=management
nomad acl token delete <old-accessor>
```
