# Nomad — ton-cluster

Single-node [HashiCorp Nomad](https://developer.hashicorp.com/nomad) 2.1.1 running inside the
`ton` cluster, with ACLs enabled and login through Pocket ID (OIDC). The web UI is published at
**https://nomad.lag0.com.br**.

## What is deployed

| Object | Detail |
|---|---|
| `StatefulSet/nomad` | 1 replica, image `docker.io/hashicorp/nomad:2.1.1` (`sha256:1a9a0a9ab149a6dd05fd5219e11273a20507a108ab191db26360f0843359ddf7`) |
| `ConfigMap/nomad-config` | agent config (`nomad.hcl`) — server + client in one agent, ACL and UI enabled |
| `PVC data` (5Gi, `local-path`) | `/var/nomad` — raft log/store, ACL state, allocations |
| `Service/nomad` | `:80` → HTTP 4646, plus `:4647` (RPC) and `:4648` (serf) |
| `VirtualService/nomad` | `nomad.lag0.com.br` on `istio-system/lag0-gateway` |

DNS is a proxied `CNAME nomad.lag0.com.br → cf.lag0.com.br` in Cloudflare (no external-dns in this
cluster) and TLS comes from the `lag0-wildcard-certificate-secret` already served by the gateway.

## Why server + client on a single node, and what jobs can run

Nomad normally runs as servers on VMs plus clients on every machine that executes work. Talos gives
pods no access to a container runtime socket (and blocks hostPath mounts of `/run/containerd`), so a
Nomad client inside this cluster cannot use the `docker`/`podman` driver. What works is a
single-agent instance whose client enables the **`raw_exec`** driver: jobs run as processes inside the
`nomad` container (the container filesystem is the task root). That is enough to exercise the
scheduler, the API, the UI and the ACL/OIDC flow.

Real workloads belong on **external clients**: install a Nomad client on any machine that can reach
the RPC port, point `client.servers` at this server and join the region. That requires exposing TCP
4647 (and 4648 for serf) beyond the Istio gateway — see "Adding external clients" below.

Kubernetes keeps running the apps; Nomad here is a second orchestrator for experiments, not a
replacement.

## ACL and OIDC (Pocket ID)

`acl.enabled = true`, so the HTTP API requires a token. Two independent credentials exist:

1. **Bootstrap / management token** — created once with `nomad acl bootstrap`. Kept in the
   `nomad-acl` Secret (`token`) and in the Vaultwarden item `nomad-ton`.
2. **User tokens via OIDC** — the auth method `pocket-id` lets a person log into the UI or the CLI
   with their Pocket ID account; Nomad issues a short-lived ACL token bound to a policy through
   the binding rule.

Pocket ID side (`https://id.lag0.com.br`):

| Setting | Value |
|---|---|
| Client | `nomad` (`9d992eb9-3fd9-4c58-9eaf-dbd4fd20f059`), confidential, no PKCE |
| Callback | `https://nomad.lag0.com.br/oidc/callback` |
| Restriction | `isGroupRestricted: true`, allowed group `nomad-users` (`a2dd487f-00ec-442b-9a31-4e2c770908e4`) |

Only members of `nomad-users` can authorize the client. The client secret lives in the
`nomad-oidc` Secret and in Vaultwarden (`nomad-ton` → `oidc_client_secret`).

### Recreating the cluster-side ACL state (after losing the PVC, or on a fresh install)

```bash
# 1. bootstrap (once, prints the management token — store it in the secret)
kubectl --context admin@ton-cluster -n nomad exec nomad-0 -- nomad acl bootstrap

# 2. admin policy
kubectl --context admin@ton-cluster -n nomad exec -i nomad-0 -- \
  nomad acl policy apply -description "Nomad admins (Pocket ID)" nomad-admin /dev/stdin <<'EOF'
namespace "*" {
  policy = "write"
}

node {
  policy = "write"
}

agent {
  policy = "write"
}

operator {
  policy = "write"
}

host_volume "*" {
  policy = "write"
}

plugin {
  policy = "write"
}

quota {
  policy = "write"
}

variables {
  path "*" {
    capabilities = ["write"]
  }
}
EOF

# 3. OIDC auth method (config file carries the client secret; do not commit it)
kubectl --context admin@ton-cluster -n nomad exec -i nomad-0 -- \
  nomad acl auth-method create -name pocket-id -type OIDC -max-token-ttl 8h \
  -token-locality global -default -config @/tmp/oidc.json

# 4. binding rule: members of the Pocket ID group nomad-users get the admin policy
kubectl --context admin@ton-cluster -n nomad exec nomad-0 -- \
  nomad acl binding-rule create -method pocket-id -bind-type policy \
  -bind-name nomad-admin -selector '"nomad-users" in list.groups'
```

`/tmp/oidc.json` (copied into the pod with `kubectl cp`, secret filled from the `nomad-oidc` Secret):

```json
{
  "OIDCDiscoveryURL": "https://id.lag0.com.br",
  "OIDCClientID": "9d992eb9-3fd9-4c58-9eaf-dbd4fd20f059",
  "OIDCClientSecret": "<from secret nomad-oidc>",
  "OIDCScopes": ["openid", "profile", "email", "groups"],
  "AllowedRedirectURIs": ["https://nomad.lag0.com.br/oidc/callback"],
  "ClaimMappings": { "email": "email" },
  "ListClaimMappings": { "groups": "groups" }
}
```

## Using the instance

```bash
export NOMAD_ADDR=https://nomad.lag0.com.br
export NOMAD_TOKEN="<management token from the nomad-acl secret>"

nomad server members
nomad node status
nomad status
```

Browser: open https://nomad.lag0.com.br/ui/ → **Sign in with OIDC** → Pocket ID (passkey) → back in
the UI with an ACL token scoped by the `nomad-admin` policy.

CLI with SSO instead of the shared token (opens a browser):

```bash
NOMAD_ADDR=https://nomad.lag0.com.br nomad login -method=pocket-id
```

## Adding external clients

The Istio gateway only proxies HTTP; RPC/serf traffic needs a TCP path. Options, in order of
preference: (a) expose the `nomad` Service as `type: LoadBalancer` restricted to the LAN, (b) reach
it over the NetBird/Tailscale mesh, (c) `kubectl port-forward`. Then on the client machine:

```hcl
client {
  enabled = true
  servers = ["<server-address>:4647"]
}
```

Nomad 2.1 requires an `agent:write` token for an authenticated join; give the client a token with
`node:write` (see the ACL docs) and enable mTLS/gossip encryption before exposing RPC outside the
LAN.

## Operations

```bash
# logs
kubectl --context admin@ton-cluster -n nomad logs -f nomad-0

# leader / health
curl -s https://nomad.lag0.com.br/v1/status/leader

# raft snapshot (do this before upgrades; the PVC is the only copy of cluster state)
kubectl --context admin@ton-cluster -n nomad exec nomad-0 -- \
  nomad operator snapshot save -compress /var/nomad/snap-$(date +%F).snap
```

Upgrades: bump `image` in `statefulset.yaml` (pin the tag, never `latest`), push, then
`kubectl rollout restart -n nomad statefulset/nomad` if Flux does not roll it. Nomad does not
support downgrades — take a snapshot first.

## Pitfalls

- **Cloudflare Browser Integrity Check** blocks `Python-urllib` user agents on `id.lag0.com.br`.
  Nomad's OIDC discovery uses Go's HTTP client, which passes, but a shell test with
  `python requests` returning 403 does not mean the auth method is broken.
- The OIDC `AllowedRedirectURIs` must match exactly; Pocket ID v2 rejects wildcards and URIs with a
  `#` fragment.
- `nomad status` against the public host goes through Cloudflare — long-polling endpoints are fine,
  but a proxy timeout can cut `nomad monitor`. Use `kubectl exec` for long streams.
- The client in this pod has no `docker` driver. Jobs that specify `driver = "docker"` stay queued
  with "no nodes available" — use `raw_exec` or add an external client.
