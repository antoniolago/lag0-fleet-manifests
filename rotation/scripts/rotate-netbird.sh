#!/usr/bin/env bash
# rotate-netbird.sh — Rotates Netbird PATs (Personal Access Tokens)
# Bootstrap config needs: NETBIRD_MGMT_URL, NETBIRD_BOOTSTRAP_PAT
#
# Rotates netbird-operator-api-key used by OKE operator
# Safe rotation: creates NEW key first, verifies, then notifies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

rotate_netbird_operator() {
  log_info "=== Netbird Operator PAT Rotation ==="
  local url="${NETBIRD_MGMT_URL:-https://netbird.lag0.com.br}"
  local pat="${NETBIRD_BOOTSTRAP_PAT:-}"
  if [[ -z "$pat" ]]; then
    log_error "NETBIRD_BOOTSTRAP_PAT not set in bootstrap config"
    return 1
  fi
  local auth=(-H "Authorization: Bearer $pat" -H "Content-Type: application/json")

  log_info "STEP 1: Listing Netbird users..."
  local users=$(curl -sf "${url}/api/users" "${auth[@]}" 2>/dev/null) || {
    log_error "Failed to list Netbird users (check bootstrap PAT)"
    return 1
  }

  local user_id=$(echo "$users" | jq -r '.[] | select(.name // .email // "" | test("admin"; "i")) | .id // empty' | head -1)
  if [[ -z "$user_id" ]]; then
    user_id=$(echo "$users" | jq -r '.[0].id // empty')
    log_warn "No admin user found, using first user"
  fi
  if [[ -z "$user_id" || "$user_id" == "null" ]]; then
    log_error "No users found"
    return 1
  fi
  log_ok "Using user: $user_id"

  log_info "STEP 2: Creating new PAT via API..."
  local ts=$(date +%Y%m%d)
  local pat_payload=$(jq -n --arg n "oke-operator-${ts}" '{name:$n,expires_in:864000}')
  local new_pat=$(curl -sf -X POST "${url}/api/users/${user_id}/tokens" "${auth[@]}" -d "$pat_payload" 2>/dev/null) || {
    log_warn "API-based PAT creation failed (not supported by all Netbird versions)"
    log_info "Creating PAT via dashboard is needed. Instructions:"
    log_info "  1. Go to ${url}/settings/api-keys"
    log_info "  2. Create new key named: oke-operator-$(date +%Y%m%d)"
    log_info "  3. Save to Vaultwarden item: netbird-operator-api-key"
    log_info "Skipping automated rotation (VKS will sync from Vaultwarden)"
    save_backup "netbird-operator-api-key" "$pat" "NB_API_KEY"
    return 0
  }

  local new_token=$(echo "$new_pat" | jq -r '.token // .plain_token // .key // empty')
  local new_id=$(echo "$new_pat" | jq -r '.id // empty')
  if [[ -z "$new_token" ]]; then
    log_error "PAT created but no token value in response"
    return 1
  fi
  log_ok "New PAT created: $new_id"

  save_backup "netbird-operator-api-key" "$pat" "NB_API_KEY"
  log_info "Updating Vaultwarden item: netbird-operator-api-key"
  bw_update_password "netbird-operator-api-key" "$new_token" || log_warn "Vaultwarden item not found"

  log_info "Verifying new PAT..."
  sleep 30
  local vr=$(curl -sf "${url}/api/users" -H "Authorization: Bearer $new_token" 2>/dev/null)
  if echo "$vr" | jq -e 'length > 0' >/dev/null 2>&1; then
    log_ok "VERIFIED: new PAT works!"
  else
    log_error "VERIFICATION FAILED!"
    return 1
  fi

  log_info "=== Netbird Operator PAT Rotation Complete ==="
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  bw_login
  rotate_netbird_operator
fi
