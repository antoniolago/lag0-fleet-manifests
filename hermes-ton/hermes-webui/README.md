# hermes-webui — Hermes WebUI at hermes.lag0.com.br

Browser front end for the ton-cluster Hermes agent. Replaces the Open WebUI that
used to serve the root of this host (`/a2a/*` was, and still is, the fleet's A2A
hub — see `hermes-ton/hermes/`).

```
browser ──https──► istio gateway (hermes.lag0.com.br)
                     ├─ /a2a/*  ──► hermes-hub:8080      (A2A hub, Pocket ID gated)
                     └─ /       ──► hermes-webui:80 ──► oauth2-proxy:4180 (sidecar)
                                                          └─ authenticated ──► WebUI:8787
```

## What it is

* `deployment.yaml` — one pod, three containers:
  * `agent-src` (init): mirrors the agent image's `/opt/hermes` into an emptyDir,
    because Kubernetes cannot mount another image's directory. The WebUI needs it
    to install the agent into its own venv and to discover the agent
    (`HERMES_WEBUI_AGENT_DIR`) for model auto-detection and CLI session imports.
  * `hermes-webui`: the UI itself, `HERMES_HOME=/opt/data` on the **same PVC as
    the agent** (`hermes-data`), so it shows ton-cluster's config, skills,
    memories and sessions rather than a second, empty agent.
  * `oauth2-proxy`: the Pocket ID login (see *Why not the built-in OIDC*).
* `service.yaml` — ClusterIP publishing **only** the oauth2-proxy port; the WebUI's
  8787 is not exposed, so nothing can skip the login.
* `pvc.yaml` — `/app` (venv + staged agent source). Keeping it is what turns the
  ~4 minute first start (installs WebUI requirements and the agent from pypi) into
  a fast restart: `/app/venv/.deps_installed` short-circuits the install.
* `virtualservice.yaml` (in the parent dir) — routes `/` here, `/a2a` to the hub.

Browser chat is **gateway-backed** (`HERMES_WEBUI_CHAT_BACKEND=gateway`): turns
are executed by the agent's API server (`hermes-api:8642`), i.e. by the same
cluster-admin, kubectl-capable runtime Matrix and A2A talk to — not by a second
agent process inside this container.

## Why the experimental image

The newest **stable** container installs hermes-agent with a plain
`uv pip install`, which goes through setuptools' `bdist_wheel` — and the agent's
`setup.py` now refuses to build a wheel outside a Nix sandbox
(*Building wheels or sdists for hermes-agent is not supported*), so the container
exits before `server.py` ever runs.

Upstream's fix (`3c6566b4`, #6458: editable install from a staged source kept
under `/app`) is unreleased — it reached the experimental channel first
(`exp-v0.52.159`), and no stable tag carries it yet:

```bash
git tag --contains 3c6566b4 | grep -v '^exp-'
```

The pinned `:0.52.409` experimental build also carries the fix for the profile
switcher returning 500 when the agent source is mounted *and* the gateway chat
backend is on (#7305) — this deployment's exact configuration. **Move back to a
stable tag as soon as one carries the fix.**

## Why not the built-in OIDC

The WebUI has native Pocket ID support (`webui_oidc` / `HERMES_WEBUI_OIDC_*`) and
it was the first thing tried. Two independent blockers, both field-verified:

1. **Cloudflare's Browser Integrity Check blocks the client's User-Agent.** The
   OIDC HTTP calls are plain `urllib` requests with no `User-Agent` header, so the
   edge sees `Python-urllib/3.12` and answers `403` — *error code: 1010*. It is a
   zone setting, not a per-host rule: the same UA is refused on every proxied host
   in `lag0.com.br`, while `curl`, `python-requests` and browser UAs all pass.
   Reproduce from anywhere:
   ```bash
   dig +short @1.1.1.1 id.lag0.com.br                       # Cloudflare edge IPs
   curl -s -A "Python-urllib/3.12" --resolve id.lag0.com.br:443:<edge-ip> \
        -o /dev/null -w '%{http_code}\n' \
        https://id.lag0.com.br/.well-known/openid-configuration
   ```
   That belongs upstream (the client should send a real UA, as the WebUI's other
   probes do), and it is also fixable at the edge by skipping BIC for the OIDC
   paths of `id.lag0.com.br`.
2. **The client refuses private endpoints** (SSRF guard in `api/auth_oidc.py`:
   *OIDC endpoint URLs must not target private or local addresses*), so pointing
   it at the in-cluster istio VIP or the `pocket-id` Service is not an option
   either. `*.lag0.com.br` resolves to `192.168.88.190` inside the cluster.

So the login is delegated to `oauth2-proxy`, in the mode the WebUI documents for
exactly this (*Delegate authentication to a reverse proxy you run (Authelia,
oauth2-proxy, …)*): `HERMES_WEBUI_TRUSTED_AUTH_HEADER=X-Forwarded-Email` — the
header `--pass-user-headers` sends to the upstream (`--set-xauthrequest` would
only decorate the `/oauth2/auth` response, nginx-auth_request style) — with
the proxy as a **sidecar on loopback**: loopback is the only peer the WebUI
trusts by default, so no broad `TRUSTED_PROXY_CIDRS` allowlist is involved, and a
pod hitting the WebUI's port directly gets `401`.

The proxy **skips discovery** and talks to Pocket ID over the in-cluster Service
(`--redeem-url` / `--oidc-jwks-url` point at `pocket-id.pocket-id.svc.cluster.local`),
so no server-side call goes through Cloudflare and the login still works when the
tunnel or the WAN is down. The issuer string stays `https://id.lag0.com.br` so the
id_token `iss` claim still matches; only the browser-facing authorize URL and the
redirect are public.

Identity is the Pocket ID client **`hermes`** (confidential; restricted to the
`hermes-users` group, i.e. only the owner) — the same client the Open WebUI used at
this host, with its callback moved to
`https://hermes.lag0.com.br/oauth2/callback`. Its secret already lives in
`hermes-secrets` (VKS-synced from Vaultwarden).

### Secret

`hermes-webui-auth/cookie-secret` (ns `hermes`) is the oauth2-proxy cookie key,
created directly with `kubectl` — an app-local value, not a shared credential, so
it is not in Vaultwarden/VKS. oauth2-proxy requires exactly 16/24/32 **raw** bytes
(it does not base64-decode):

```bash
kubectl -n hermes create secret generic hermes-webui-auth \
  --from-literal=cookie-secret="$(openssl rand -hex 16)"
```

Losing it only invalidates existing login sessions.

## Operating notes

* **Changing anything the WebUI reads only at pod start** (image, env, mounted
  files) requires bumping the `hermes.lag0.com.br/config-version` annotation in the
  pod template — nothing else rolls the pod.
* **Flux owns `virtualservice.yaml` and this directory** (`prune: false`): a manual
  `kubectl apply` is reverted within a minute, and deleting a file here does *not*
  delete the object from the cluster.
* The WebUI writes its state (sessions, settings, workspaces) to
  `/opt/data/webui` inside the agent home — same volume the agent writes.
* If the login ever breaks, check in this order: `oauth2-proxy` logs (config,
  redirect URL), then Pocket ID's client callback URL, then Cloudflare's BIC (only
  relevant if the built-in OIDC is re-enabled).
