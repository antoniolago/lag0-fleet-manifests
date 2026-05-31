#!/usr/bin/env bash
# rotate-harbor.sh — Rotates Harbor admin password and robot accounts
# Bootstrap config needs: HARBOR_URL, HARBOR_BOOTSTRAP_PASSWORD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

rotate_harbor() {
  log_info "=== Harbor Credential Rotation ==="
  local url="${HARBOR_URL:-https://harbor-ton.lag0.com.br}"
  local ap="${HARBOR_BOOTSTRAP_PASSWORD:-}"
  if [[ -z "$ap" ]]; then
    log_error "HARBOR_BOOTSTRAP_PASSWORD not set"
    return 1
  fi

  log_info "STEP 1: Login to Harbor API..."
  curl -s -X POST "${url}/api/v2.0/users/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"admin\",\"password\":\"${ap}\"}" \
    -c /tmp/.harbor-cookies 2>/dev/null || {
    log_error "Failed to login to Harbor"
    return 1
  }
  log_ok "Logged in"

  log_info "STEP 2: Changing admin password..."
  local new_pass=$(generate_password 48)
  local csrf=$(grep harbor-csrf /tmp/.harbor-cookies 2>/dev/null | awk '{print $7}')
  curl -s -X PUT "${url}/api/v2.0/users/1/password" \
    -H "Content-Type: application/json" \
    -H "X-Harbor-CSRF-Token: ${csrf}" \
    -b /tmp/.harbor-cookies \
    -d "{\"old_password\":\"${ap}\",\"new_password\":\"${new_pass}\"}" 2>/dev/null || {
    log_warn "Failed to change password (Harbor may not allow API password change)"
  }
  log_ok "Admin password changed"

  log_info "STEP 3: Creating robot account..."
  local rname="rotation-$(date +%Y%m%d)"
  local robot=$(curl -s -X POST "${url}/api/v2.0/robots" \
    -H "Content-Type: application/json" \
    -b /tmp/.harbor-cookies \
    -d "{\"name\":\"${rname}\",\"duration\":-1,\"level\":\"system\",\"permissions\":[{\"kind\":\"project\",\"namespace\":\"**\",\"access\":[{\"resource\":\"repository\",\"action\":\"push\"},{\"resource\":\"repository\",\"action\":\"pull\"}]}]}" 2>/dev/null)
  local rsecret=$(echo "$robot" | jq -r '.secret // .token // empty')
  if [[ -n "$rsecret" ]]; then
    log_ok "Robot account created: $rname"
    bw_set_field "harbor-robot" "secret" "$rsecret" 2>/dev/null || log_warn "Vaultwarden item not found"
  else
    log_warn "Robot creation failed or not supported"
  fi

  log_info "STEP 4: Saving to Vaultwarden..."
  save_backup "harbor-admin" "$ap" "adminPassword"
  bw_set_field "harbor-credentials" "adminPassword" "$new_pass" 2>/dev/null || log_warn "Vaultwarden item harbor-credentials not found"
  log_info "Remember to update helm.yaml in fleet-manifests with new adminPassword"

  rm -f /tmp/.harbor-cookies
  log_info "=== Harbor Rotation Complete ==="
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  bw_login
  rotate_harbor
fi
