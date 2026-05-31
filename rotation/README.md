# Secret Rotation Suite

Automated rotation of API keys and secrets across Lag0 infrastructure.
Runs every 10 days via Hermes cronjob.

## What Gets Rotated

| Service | What | Where | Rotation Method |
|---------|------|-------|-----------------|
| **Cloudflare** | API Token | cert-manager DNS-01 | Cloudflare API (clone permissions) |
| **Netbird** | PAT | OKE operator auth | Netbird Management API |
| **GitHub** | PAT | cluster-external-secrets | Manual (no REST API for PAT creation) |
| **Harbor** | admin + robot | harbor-ton CI/CD | Harbor REST API |

## Architecture

```
Hermes Cronjob (every 10 days)
  └── run-all.sh
       ├── rotate-cloudflare.sh → CF API → Vaultwarden → VKS → K8s
       ├── rotate-netbird.sh    → NB API → Vaultwarden → VKS → K8s
       ├── rotate-github.sh     → (manual) → Vaultwarden
       └── rotate-harbor.sh     → Harbor API → Vaultwarden
```

## Safe Rotation Pattern

Every script follows this pattern (no-break guarantee):

1. **Read** current credential from Vaultwarden
2. **Create** new credential via service API
3. **Backup** old credential to rollback file
4. **Write** new credential to Vaultwarden
5. **Wait** 30s for VKS/external-secrets to sync
6. **Verify** new credential works (API test)
7. **Revoke** old credential ONLY if verification passed

If step 6 fails, the old credential is kept — zero downtime.

## Setup

### 1. Bootstrap credentials

Copy the example config and fill in your credentials:

```bash
cp rotation/bootstrap-config.sh.example ~/.hermes/scripts/rotation-config.sh
chmod 600 ~/.hermes/scripts/rotation-config.sh
nano ~/.hermes/scripts/rotation-config.sh
```

Required credentials:

| Variable | Where to get it |
|----------|----------------|
| `BW_CLIENT_ID` | Vaultwarden Admin → API Key |
| `BW_CLIENT_SECRET` | Vaultwarden Admin → API Key |
| `CLOUDFLARE_BOOTSTRAP_TOKEN` | Cloudflare Dashboard → API Tokens (needs: zone:read, api_tokens:create) |
| `CLOUDFLARE_ZONE_ID` | Cloudflare Dashboard → Overview → Zone ID |
| `NETBIRD_BOOTSTRAP_PAT` | netbird.lag0.com.br → Settings → API Keys |
| `GITHUB_BOOTSTRAP_TOKEN` | github.com → Settings → Developer settings → PAT |
| `HARBOR_BOOTSTRAP_PASSWORD` | Current Harbor admin password |

### 2. First manual run

```bash
bash rotation/scripts/run-all.sh
```

### 3. Hermes cronjob

```bash
hermes cron create   --schedule "every 10 days"   --script rotation/scripts/run-all.sh
```

## Rollback

If something breaks, the old values are saved in `/tmp/secret-rotation-rollback-*.json`:

```bash
# List all backups
cat /tmp/secret-rotation-rollback-*.json | jq '.[] | {service, field, timestamp}'

# Restore a specific value to Vaultwarden
OLD_VALUE=$(cat /tmp/secret-rotation-rollback-*.json | jq -r '.[] | select(.service=="cloudflare-api-token") | .old_value')
bw_update_password "cloudflare-secrets" "$OLD_VALUE"
```

## Files

```
rotation/
├── README.md
├── .gitignore
├── bootstrap-config.sh.example
└── scripts/
    ├── lib.sh                    # Shared functions
    ├── run-all.sh                # Orchestrator
    ├── rotate-cloudflare.sh      # Cloudflare API Token
    ├── rotate-netbird.sh         # Netbird PATs
    ├── rotate-github.sh          # GitHub credentials
    └── rotate-harbor.sh          # Harbor credentials
```
