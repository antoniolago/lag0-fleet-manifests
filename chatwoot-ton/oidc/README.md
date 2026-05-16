# OIDC SSO Extension for Chatwoot

Generic OpenID Connect authentication for Chatwoot. Works with any OIDC provider:
Pocket ID, Keycloak, Authentik, Auth0, Okta, Azure AD, etc.

## Enable

Add `oidc` to your `kustomization.yaml` resources:

```yaml
resources:
  - namespace.yaml
  - helm.yaml
  - helm-valkey.yaml
  - virtualservice.yaml
  - oidc  # ← Add this line
```

## Configure

1. **Create the secret** (use sealed-secrets in production):

```bash
# Edit oidc/secret.yaml with your values, then seal it:
kubeseal < oidc/secret.yaml > oidc/sealed-secret.yaml

# Or create directly:
kubectl create secret generic chatwoot-oidc-secrets \
  --namespace chatwoot \
  --from-literal=values='
env:
  ENABLE_OIDC_LOGIN: "true"
  OIDC_DISPLAY_NAME: "Pocket ID"
  OIDC_CLIENT_ID: "chatwoot"
  OIDC_CLIENT_SECRET: "your-secret"
  OIDC_ISSUER_URL: "https://pocket-id.example.com"
' --dry-run=client -o yaml | kubeseal -o yaml > oidc/sealed-secret.yaml
```

2. **Configure your Identity Provider**:

| Setting | Value |
|---------|-------|
| Redirect URI | `https://chatwoot.example.com/auth/oidc/callback` |
| Grant Type | Authorization Code |
| PKCE | Enabled |
| Scopes | `openid email profile` |

## Disable

Remove `oidc` from your `kustomization.yaml` resources.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENABLE_OIDC_LOGIN` | Yes | `false` | Enable OIDC |
| `OIDC_CLIENT_ID` | Yes | - | OAuth Client ID |
| `OIDC_CLIENT_SECRET` | Yes | - | OAuth Client Secret |
| `OIDC_ISSUER_URL` | Yes | - | OIDC Issuer URL |
| `OIDC_DISPLAY_NAME` | No | `SSO` | Login button text |
| `OIDC_SCOPE` | No | `openid email profile` | OAuth scopes |

## Provider Examples

### Pocket ID
```yaml
OIDC_ISSUER_URL: "https://pocket-id.example.com"
```

### Keycloak
```yaml
OIDC_ISSUER_URL: "https://keycloak.example.com/realms/myrealm"
```

### Authentik
```yaml
OIDC_ISSUER_URL: "https://authentik.example.com/application/o/chatwoot/"
```

