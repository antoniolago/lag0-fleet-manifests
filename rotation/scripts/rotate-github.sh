#!/usr/bin/env bash
# rotate-github.sh — GitHub credential management
# Bootstrap config needs: GITHUB_USERNAME, GITHUB_BOOTSTRAP_TOKEN
#
# NOTE: GitHub PAT cannot be created via REST API without OAuth flow.
# This script generates a strong password and updates Vaultwarden.
# Actual PAT creation must be done via GitHub UI or gh CLI.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

rotate_github() {
  log_info "=== GitHub Credential Rotation ==="
  local user="${GITHUB_USERNAME:-antoniolago}"
  local bt="${GITHUB_BOOTSTRAP_TOKEN:-}"
  if [[ -z "$bt" ]]; then
    log_error "GITHUB_BOOTSTRAP_TOKEN not set in bootstrap config"
    return 1
  fi

  log_info "GitHub PAT cannot be created via REST API without OAuth flow."
  log_info "To rotate manually, go to: https://github.com/settings/tokens"
  log_info "Create new fine-grained PAT with repo:read + admin:org scopes"
  log_info 'Save to Vaultwarden: cluster-external-secrets field github_password'
  log_info "Also update GITHUB_BOOTSTRAP_TOKEN in rotation config"

  local new_pass=$(generate_password 64)
  log_info "Generated: ${new_pass:0:16}..."

  save_backup "github-credential" "$bt" "github_password"
  log_info "Updating Vaultwarden item: cluster-external-secrets..."
  bw_update_password "cluster-external-secrets" "$new_pass" 2>/dev/null || \
    bw_set_field "cluster-external-secrets" "github_password" "$new_pass" 2>/dev/null || \
    log_warn "Vaultwarden item cluster-external-secrets not found"

  log_info "=== GitHub Rotation Complete ==="
  log_info "Run gh CLI or use GitHub UI for actual PAT rotation"
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  bw_login
  rotate_github
fi
