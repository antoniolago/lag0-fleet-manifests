# galzolina — secrets

`wordpress` expects a Secret named **`galzolina-secrets`** in namespace **`galzolina`** with
these keys:

| Key | Consumers | Notes |
|-----|-----------|-------|
| `MARIADB_PASSWORD` | MariaDB (`MARIADB_PASSWORD`, creates the `wordpress` DB user) and WordPress (`WORDPRESS_DB_PASSWORD`) | must be the same value for both |
| `MARIADB_ROOT_PASSWORD` | MariaDB (`MARIADB_ROOT_PASSWORD`) | only needed for admin/maintenance |

Nothing sensitive is committed to this repo — **`lag0-fleet-manifests` is a public GitHub
repository**. WordPress auth keys/salts are not managed here either: the official `wordpress`
image generates 8 unique random salts into `wp-config.php` on first boot, and that file lives
on the `galzolina-html` PVC.

## Canonical path — Vaultwarden item + VKS

1. Generate the two values (run twice):

   ```bash
   openssl rand -hex 32
   ```

2. In Vaultwarden (`https://vw.lag0.com.br`), organization `kubernetes-secrets`, create a
   **Secure Note** item:

   | Field | Value |
   |-------|-------|
   | Name | `galzolina-secrets` |
   | `MARIADB_PASSWORD` (Hidden) | *(first generated value)* |
   | `MARIADB_ROOT_PASSWORD` (Hidden) | *(second generated value)* |
   | `namespaces` (Text) | `galzolina` |

3. `vaultwarden-kubernetes-secrets` mirrors the item into the K8s Secret within ~30s and owns
   it from then on (delete-orphans is enabled, so all three fields must exist in the item).

WordPress and MariaDB reference the Secret with **non-optional** `secretKeyRef`, so pods stay in
`CreateContainerConfigError` until it exists — that is expected before the item is created.

## Rotating the DB password

Both containers read the same `MARIADB_PASSWORD`. Changing it in the item alone is **not**
enough: MariaDB already created the `wordpress` user with the old value. Order matters:

```bash
# 1. change it inside MariaDB first
kubectl exec -n galzolina deploy/galzolina-db -- \
  mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" \
  -e "ALTER USER 'wordpress'@'%' IDENTIFIED BY '<new-value>'; FLUSH PRIVILEGES;"

# 2. update the Vaultwarden item, let VKS sync, then restart WordPress
kubectl rollout restart -n galzolina deploy/wordpress
```

## Bootstrap fallback (unmanaged)

Only for bringing the site up before the Vaultwarden item exists. If you use it, copy both
values into the item afterwards — VKS overwrites the Secret from the item, and a mismatch leaves
MariaDB initialized with the old password.

```bash
kubectl create secret generic galzolina-secrets -n galzolina \
  --from-literal=MARIADB_PASSWORD="$(openssl rand -hex 32)" \
  --from-literal=MARIADB_ROOT_PASSWORD="$(openssl rand -hex 32)"
```
