#!/bin/bash
set -euo pipefail

# VW API Key Rotation - uses kubectl + curl (via K8s API)
KUBE_TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
KUBE_CA="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBE="https://kubernetes.default.svc"
H="Authorization: Bearer $KUBE_TOKEN"
CT="Content-Type: application/json"

# Helper: K8s API call
kapi() {
  curl -sf --cacert "$KUBE_CA" -H "$H" -H "$CT" -X "$1" "$KUBE$2" "${3:--d \"\"}"
}

# Get postgres password
PG_PASS=$(kapi GET /api/v1/namespaces/vaultwarden/secrets/vaultwarden-secrets | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['data']['POSTGRES_PASSWORD']).decode())")

# Get user email
EMAIL="antonio.clago@outlook.com"

# Generate new key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(30))")
NEW_B64=$(echo -n "$NEW_KEY" | base64)

# Update in Postgres
kubectl exec -n vaultwarden vaultwarden-postgres-0 -- psql -U vaultwarden -d vaultwarden -c "UPDATE users SET api_key='$NEW_KEY' WHERE email='$EMAIL'"

# Update K8s secret
kapi PATCH "/api/v1/namespaces/vaultwarden-kubernetes-secrets/secrets/vaultwarden-kubernetes-secrets" \
  -d "{\"data\":{\"BW_CLIENTSECRET\":\"$NEW_B64\"}}"

# Restart VKS
kapi PATCH "/apis/apps/v1/namespaces/vaultwarden-kubernetes-secrets/deployments/vaultwarden-kubernetes-secrets" \
  -d '{"spec":{"template":{"metadata":{"annotations":{"kubectl.kubernetes.io/restartedAt":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}}}}'

echo "OK rotated"
