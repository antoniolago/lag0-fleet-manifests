# Project NOMAD — offline knowledge server (time capsule)

[Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad) v1.35.1 running on a
dedicated VM, published at **https://nomad.lag0.com.br** behind Pocket ID (OIDC). The Command Center
is a management UI/API that orchestrates Docker containers on its own host — Kiwix/Wikipedia,
Kolibri, Ollama, maps, notes, PDF tools — so it needs a real Docker socket, which is why it lives on
a VM and not in the Talos cluster.

## Topology

| Piece | Where | Detail |
|---|---|---|
| `nomad-knowledge` | Proxmox **ton03**, VM **121** | Ubuntu 24.04.5 cloud image, 4 vCPU / 4 GB RAM / 40 GB (local-lvm), IP `192.168.88.246/24` |
| NOMAD stack | VM, Docker Compose | admin `:8080`, MySQL, Redis, Dozzle `127.0.0.1:9999`, updater, disk-collector |
| `project-nomad` ns | ton-cluster | Flux Kustomization → `project-nomad-ton/` |
| `oauth2-proxy` | ton-cluster | v7.15.6, upstream = the VM (`project-nomad-vm` Service + manual EndpointSlice) |
| `nomad.lag0.com.br` | Cloudflare → tunnel → Istio | VirtualService → `oauth2-proxy:4180` → VM `:8080` |

Traffic: browser → Cloudflare (proxied CNAME) → `cf.lag0.com.br` tunnel → Istio gateway →
`oauth2-proxy` → Pocket ID (`id.lag0.com.br`) → VM `192.168.88.246:8080`.

## Provisioning the VM

The VM was created through the Proxmox API (no SSH access to the hosts) from the Ubuntu 24.04 cloud
image, with cloud-init for the user, the SSH key and the static IP. After that:

```bash
scp vm/compose.yml.tmpl vm/provision.sh antonio@192.168.88.246:~/nomad-install/
ssh antonio@192.168.88.246 'sudo bash ~/nomad-install/provision.sh https://nomad.lag0.com.br'
```

`provision.sh` is idempotent: installs Docker CE if missing, creates `/opt/project-nomad/{storage,mysql,redis}`,
generates `/opt/project-nomad/.env` **once** (`APP_KEY`, `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`), renders
`compose.yml` from the template and runs `docker compose up -d`, then waits for `/api/health`.

Layout on the VM:

```
/opt/project-nomad/.env         secrets (0600, never in git)
/opt/project-nomad/compose.yml  rendered stack (the updater rewrites the image tag here)
/opt/project-nomad/storage      ZIMs, AI models, notes  ← NOMAD_STORAGE_PATH
/opt/project-nomad/mysql        database
/opt/project-nomad/redis        queue state
```

Content is what fills the disk: the 40 GB volume holds the stack (~5 GB) plus whatever the Supply
Depot downloads. To grow, resize the volume (`PUT /nodes/ton03/qemu/121/resize disk=scsi0&size=80G`
then `growpart`/`resize2fs`) or move `storage` to the NAS and keep the host path in sync in the
compose file **and** in `NOMAD_STORAGE_PATH` + the disk-collector mount.

## OIDC (Pocket ID)

Pocket ID client **`nomad`** (`9d992eb9-3fd9-4c58-9eaf-dbd4fd20f059`): confidential, no PKCE,
callback `https://nomad.lag0.com.br/oauth2/callback`, logout callback `https://nomad.lag0.com.br/`,
`launchURL` set, **group-restricted to `nomad-users`** (`a2dd487f-00ec-442b-9a31-4e2c770908e4`), whose
only member is `antonio.lago`. Scope: `openid email profile groups`.

oauth2-proxy (`oauth2-proxy.yaml`) runs with `--provider=oidc`, issuer `https://id.lag0.com.br`,
`--redirect-url=https://nomad.lag0.com.br/oauth2/callback`, `--cookie-secure=true`, 24h cookie with
1h refresh, `--approval-prompt=auto` (so the Pocket ID consent appears once, not on every login).
Secrets (`client-id`, `client-secret`, `cookie-secret`) come from the `oauth2-proxy-nomad` Secret.

`email_verified` on the user must be `true`: oauth2-proxy v7.15 refuses the callback with
`email in id_token (...) isn't verified` otherwise, and the lag0 Pocket ID has no SMTP.
`antonio.lago` is set that way.

## Verification (executed)

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://nomad.lag0.com.br/
# 302 https://id.lag0.com.br/authorize?...redirect_uri=https%3A%2F%2Fnomad.lag0.com.br%2Foauth2%2Fcallback
# browser: SSO → back to /home → "Project NOMAD™ Command Center v1.35.1"
# Supply Depot → Install "Data Tools" (CyberChef) → container created on the VM:
#   nomad_cyberchef  ghcr.io/gchq/cyberchef:10.24.0  Up  0.0.0.0:8100->80/tcp
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.88.246:8100/   # 200
```

## Operations

```bash
ssh antonio@192.168.88.246            # key ~/.ssh/id_ed25519_nomad
sudo docker compose -f /opt/project-nomad/compose.yml ps
sudo docker compose -f /opt/project-nomad/compose.yml logs -f admin
kubectl --context admin@ton-cluster -n project-nomad logs deploy/oauth2-proxy
```

Updates: the bundled **updater** container rewrites the image tag in `/opt/project-nomad/compose.yml`
when you use "Check for Updates" in the UI, so the running version is visible in git-managed docs
only after you re-render. To pin a new release by hand, bump the admin image in
`vm/compose.yml.tmpl`, re-run `provision.sh` (it keeps `.env` and data).

Backup: `/opt/project-nomad/.env`, `mysql/` (database) and `storage/` (content). A `mysqldump` plus
a filesystem copy of `storage` is enough; nothing else holds state.

## Pitfalls (learned the hard way)

- **`cicustom`/snippet upload over the API returned 400** for the `local` dir storage; the working
  path was cloud-init through the VM parameters.
- **PVE's `sshkeys` parameter must be DOUBLE urlencoded** when set through the API: the validator
  only accepts `[-%a-zA-Z0-9_.!~*'()]` (`pve_verify_urlencoded`), and the form layer decodes once, so
  send `quote(quote(key))`. A single encoding fails with the misleading
  `invalid format - invalid urlencoded string: <your key>`.
- **`import-from` needs an `import`-content storage**: the cloud image was downloaded with
  `content=import` and imported as `scsi0=local-lvm:0,import-from=local:import/<img>.qcow2`;
  `local:iso/...` is rejected (`wrong type 'iso'`).
- **The token user cannot use filesystem paths in `import-from`** ("Only root can pass arbitrary
  filesystem paths") — use the volume id form.
- **The clone of the existing `ws-template` is broken** (`no such logical volume pve/base-9000-disk-0`);
  build the VM from the cloud image instead.
- **Child apps bypass the SSO gate**: the Supply Depot containers publish their own ports
  (`:8090` Kiwix, `:8100` documented, …) on `0.0.0.0` of the VM. They are LAN-only (nothing routes
  them publicly), but anyone on the LAN can skip oauth2-proxy. If that matters, add a VirtualService
  + oauth2-proxy per port, or bind the VM's Docker publish addresses to the tailscale/Netbird IP.
- Dozzle stays bound to `127.0.0.1:9999` on purpose (docker socket + logs).
- The retired `lag0-fleet-manifests/nomad-ton/` (HashiCorp Nomad orchestrator) was never the intended
  service; its namespace and Kustomization were removed. History keeps the manifests if it is ever
  wanted back.
