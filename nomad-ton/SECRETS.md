# Secrets — nomad

`lag0-fleet-manifests` is a **public** repository: nothing in this directory holds a live value.

Vaultwarden organization `kubernetes-secrets`, item **`nomad-ton`** (Secure Note). Custom fields:

| Field | Type | Content |
|---|---|---|
| `acl_bootstrap_token` | Hidden | management token `admin-2026-11-14b` (the raw bootstrap token was deleted after rotation) |
| `oidc_client_secret` | Hidden | Pocket ID client `nomad` secret (rotate with `POST /api/oidc/clients/<id>/secrets`) |
| `namespaces` | Text | `nomad` |

Kubernetes Secrets in namespace `nomad` (created with `kubectl create secret`, outside Flux, because
Vaultwarden Kubernetes Secrets cannot be seeded by the agent):

| Secret | Key | Content |
|---|---|---|
| `nomad-acl` | `token` | management ACL token used by operators and scripts |
| `nomad-oidc` | `OIDC_CLIENT_SECRET` | Pocket ID client secret, needed to re-create the OIDC auth method |

Nothing in the manifests references them, so a missing secret does not break the workload — but
without the management token a rebuilt cluster cannot be administered, and without the OIDC secret
the auth method cannot be re-created (the value in raft is not readable back).

The ACL bootstrap token is single-use and irreversible: `nomad acl bootstrap` refuses to run once
**any** token exists. Keep the current management token safe; if it is lost, use another management
token, or no tokens work → no admin access without a raft snapshot restore.

## Rotation

```bash
# OIDC client secret (Pocket ID generates it; the old entry is revoked with DELETE)
curl -s -b /tmp/pid.txt -X POST https://id.lag0.com.br/api/oidc/clients/9d992eb9-3fd9-4c58-9eaf-dbd4fd20f059/secrets
#   → update /tmp/oidc.json, `nomad acl auth-method update -config @/tmp/oidc.json pocket-id`,
#     then Vaultwarden + the nomad-oidc Secret, then DELETE the old secret id.

# Management token
nomad acl token create -type management -name admin-$(date +%F)   # store the SecretID
nomad acl token delete <old-accessor>                             # nomad acl token list
```
