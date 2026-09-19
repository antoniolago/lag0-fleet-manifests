# galzolina — recipe blog (WordPress)

WordPress-powered recipe blog: **"Galzolina — Receitas simples por Alexia Rocha"**.

| | |
|---|---|
| URL | `https://galzolina.lag0.com.br` |
| Namespace | `galzolina` |
| Source of truth | this directory (Flux) + `lag0-fleet-infra-ton/cluster/galzolina/` (Kustomization) |
| Secrets | **`SECRETS.md`** — nothing sensitive lives in this repo (it is public) |

## Architecture

```
Browser ──► Cloudflare (proxied DNS) ──► cloudflared tunnel (nb-mgmt)
              └─ ingress rule "*.lag0.com.br" ──► istio-gateway (istio-system:80)
                                                     └─ VirtualService galzolina
                                                          └─ Service wordpress:80 (ClusterIP)
                                                               └─ Pod wordpress
                                                                    ├─ PVC galzolina-html  (20Gi, NFS large-storage)
                                                                    └─ MariaDB galzolina-db:3306
                                                                         └─ PVC galzolina-db-data (8Gi, NFS large-storage)
```

* WordPress `wordpress:7.1.1-php8.3-apache` (Docker Hub official image) — Apache + mod_php, no sidecar.
* Database `mariadb:11.4.13` (official MariaDB LTS image) — WP requires MySQL 8 / MariaDB 10.6+.
* Both workloads use `strategy: Recreate` because the NFS PVCs are `ReadWriteOnce` and single-writer.
* `network-policies` are not enabled for this namespace (single-tenant namespace, ClusterIP-only DB).

## DNS

`galzolina.lag0.com.br` is a Cloudflare-proxied CNAME to `cf.lag0.com.br` (the hostname that
points at the `nb-mgmt` Cloudflare Tunnel) — the same pattern as every other public
`*.lag0.com.br` service:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `galzolina` | `cf.lag0.com.br` | Proxied |

Created 2026-09-18 through the Cloudflare API (zone `lag0.com.br`, record id
`4f1f002aa2986a42e598c1f18d56f37c`). `cloudflared` already has an ingress rule for
`*.lag0.com.br` → `istio-gateway`, so nothing is needed on the tunnel side. TLS uses the
existing `lag0-wildcard-certificate-secret` on `istio-system/lag0-gateway`.

## First run

1. Push this directory and the infra Kustomization; wait for Flux (`kubectl get pods -n galzolina`).
2. Create the Secret — see `SECRETS.md`. Until it exists both pods sit in `CreateContainerConfigError`.
3. Complete the WordPress install (one-time, ~30s) at
   `https://galzolina.lag0.com.br/wp-admin/install.php`:

   | Field | Value |
   |-------|-------|
   | Site Title | `Galzolina` |
   | Username | `alexia` |
   | Password | *(choose; store in Vaultwarden)* |
   | Search engine visibility | keep checked — this is a public blog |

   Headless equivalent:

   ```bash
   curl -s -X POST 'https://galzolina.lag0.com.br/wp-admin/install.php?step=2' \
     -d weblog_title=Galzolina -d user_name=alexia -d admin_password='<pw>' \
     -d admin_password2='<pw>' -d admin_email='<email>' -d blog_public=1 -d Submit=Install
   ```

4. The `galzolina-bootstrap` mu-plugin (see below) applies site configuration on the next request.

## `galzolina-bootstrap` mu-plugin

`bootstrap-configmap.yaml` ships a must-use plugin. The `volume-permissions` init container
copies it from the read-only `/bootstrap` mount to
`/var/www/html/wp-content/mu-plugins/galzolina.php` on every pod start. It runs once
(guarded by the `galzolina_bootstrap` option) and:

* forces `$_SERVER['HTTPS'] = 'on'` — TLS terminates at Cloudflare/Istio and the container only
  ever sees plain HTTP, which otherwise causes a canonical-redirect loop;
* sets title, tagline (`Receitas simples por Alexia Rocha`), timezone `America/Sao_Paulo`,
  date format `d/m/Y`, pretty permalinks `/%postname%/`, comments closed, site public;
* deletes the WordPress sample content (`Hello world!`, `Sample Page`, `Privacy Policy`) and the
  first sample comment — only when the post titles match;
* removes `edit_plugins`/`edit_themes`/`edit_files` caps (equivalent to `DISALLOW_FILE_EDIT`).

It is configuration, not a plugin: it cannot be deactivated from wp-admin. Editing
`bootstrap-configmap.yaml` requires a pod restart, because the file is only copied when a pod
starts:

```bash
kubectl rollout restart -n galzolina deploy/wordpress
```

## Day 2

**Uploads.** The media library lives on the PVC (`/var/www/html/wp-content/uploads`), so image
uploads never need extra config. Everything the site stores — core, themes, plugins, uploads,
`wp-config.php` and the salts — is on `galzolina-html`.

**Themes / plugins.** Install from `wp-admin` (`Appearance → Themes`, `Plugins → Add New`).
For recipe cards with Google rich results, `WP Recipe Maker` (free) or `Recipe Card Blocks` add
the `schema.org/Recipe` JSON-LD that a stock WordPress does not emit.

**Updating WordPress.** Bump the image tag here (Flux applies it). The image tag is pinned on
purpose — avoid `latest`:

```bash
# find the newest tag
curl -s 'https://hub.docker.com/v2/repositories/library/wordpress/tags?page_size=50&name=php8.3-apache' | jq -r '.results[].name'
```

Plugins hitting /wp-admin/update.php work too, but image bumps are the reproducible path.

**Backups.** Two things to back up: the `galzolina-html` PVC (uploads/plugins/themes) and the
database.

```bash
kubectl exec -n galzolina deploy/galzolina-db -- \
  sh -c 'exec mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction wordpress' \
  > galzolina-$(date +%F).sql
```

## Pitfalls

* **Deleting a PVC does not clear its directory.** The NFS CSI provisions
  `/ton-cluster/<namespace>_<pvc>` and re-uses it when the PVC is recreated — remove the
  directory on the NAS (`ton00`) if you really want a clean slate.
* **`Recreate` is not optional.** With `RollingUpdate` two pods would mount the same
  `ReadWriteOnce` volume; the second one hangs in `ContainerCreating`.
* **The `volume-permissions` init container is required.** The NFS CSI creates the share as
  `root:root 0755`, and `www-data` (uid 33) has to write there.
* **Never mount a ConfigMap key with `subPath` into an empty PVC.** The kubelet creates a
  *directory* named after the file — `wp-content/mu-plugins/galzolina.php` would be a directory
  instead of a plugin. That is why the plugin is copied by the init container from a directory
  mount.
* **Do not add `WORDPRESS_CONFIG_EXTRA` holding secrets** — wp-config.php is generated once, on
  the PVC, so later env changes are silently ignored. Anything that must be authoritative goes
  in the mu-plugin ConfigMap.
* **Site URL changes.** `wp_options.siteurl`/`home` are set at install time; changing the domain
  later needs a `wp search-replace` (WP-CLI) or the `WP_HOME`/`WP_SITEURL` constants.
