# Secrets — project-nomad

`lag0-fleet-manifests` is a **public** repository: no live value lives here.

Vaultwarden organization `kubernetes-secrets`, item **`project-nomad`** (Secure Note) should hold
what is scattered across three places today:

| Field | Type | Content |
|---|---|---|
| `oidc_client_secret` | Hidden | Pocket ID client `nomad` secret (rotate: `POST /api/oidc/clients/<id>/secrets`) |
| `cookie_secret` | Hidden | oauth2-proxy `--cookie-secret` (`openssl rand -base64 32` / 32-byte base64url) |
| `app_key` | Hidden | NOMAD admin `APP_KEY` from `/opt/project-nomad/.env` |
| `mysql_root_password` | Hidden | `MYSQL_ROOT_PASSWORD` from the same `.env` |
| `db_password` | Hidden | `DB_PASSWORD` (admin) = `MYSQL_PASSWORD` (mysql) |
| `vm_ssh_key` | Hidden | private key `~/.ssh/id_ed25519_nomad` on ton-desktop |
| `namespaces` | Text | `project-nomad` |

Where each value lives today:

| Location | What |
|---|---|
| VM `192.168.88.246:/opt/project-nomad/.env` (0600) | `APP_KEY`, `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD` — generated once by `provision.sh` |
| K8s Secret `project-nomad/oauth2-proxy-nomad` | `client-id`, `client-secret`, `cookie-secret` (created with `kubectl create secret`, outside Flux) |
| Pocket ID | client `nomad` secret (only the hash is stored server-side; the plaintext exists in the K8s Secret and Vaultwarden) |
| ton-desktop `~/.ssh/id_ed25519_nomad` | access to the VM |

Nothing in the manifests references these Secrets except `oauth2-proxy-nomad`, so a missing secret
only breaks the SSO front-end (the app keeps serving `http://192.168.88.246:8080` on the LAN).

Rotation:

```bash
# oauth2-proxy cookie secret (invalidates existing sessions)
openssl rand -base64 32 | tr -- '+/' '-_'   # paste into the Secret
kubectl --context admin@ton-cluster -n project-nomad create secret generic oauth2-proxy-nomad \
  --from-literal=client-id=<id> --from-literal=client-secret=<new> --from-literal=cookie-secret=<new> \
  --dry-run=client -o yaml | kubectl --context admin@ton-cluster apply -f -
kubectl --context admin@ton-cluster -n project-nomad rollout restart deploy/oauth2-proxy

# Pocket ID client secret: rotate in the UI/API and update the Secret the same way.
# NOMAD APP_KEY: changing it logs out the Command Center; do it with the stack stopped.
```
