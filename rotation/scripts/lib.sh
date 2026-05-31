#!/usr/bin/env bash
# ============================================================================
# lib.sh — Shared functions for the Lag0 Secret Rotation Suite
# ============================================================================
# Source this file from any rotate-*.sh script:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/lib.sh"
#
# Required external tools: curl, jq, bw (Bitwarden CLI)
# Bootstrap config: see bootstrap-config.sh.example
# ============================================================================

set -euo pipefail

# ---- Colors / Logging ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
NC='\033[0m' # No Color

LOGFILE="${LOGFILE:-/tmp/secret-rotation-$(date +%Y%m%d-%H%M%S).log}"

log_info()  { echo -e "${CYAN}[INFO]${NC}  $(date '+%H:%M:%S')  $*" | tee -a "$LOGFILE"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date '+%H:%M:%S')  $*" | tee -a "$LOGFILE"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%H:%M:%S')  $*" | tee -a "$LOGFILE"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S')  $*" | tee -a "$LOGFILE"; }

# ---- Bootstrap Config ----
# Load the bootstrap config (NOT in git — this file is gitignored)
BOOTSTRAP_CONFIG="${BOOTSTRAP_CONFIG:-$HOME/.hermes/scripts/rotation-config.sh}"
if [[ -f "$BOOTSTRAP_CONFIG" ]]; then
  source "$BOOTSTRAP_CONFIG"
else
  log_warn "Bootstrap config not found at $BOOTSTRAP_CONFIG"
  log_warn "Copy bootstrap-config.sh.example and set your credentials"
fi

# ---- Vaultwarden (BW CLI) ----
BW_SESSION=""

bw_login() {
  if [[ -z "${BW_CLIENT_ID:-}" || -z "${BW_CLIENT_SECRET:-}" ]]; then
    log_error "BW_CLIENT_ID and BW_CLIENT_SECRET must be set in bootstrap config"
    return 1
  fi
  export BW_CLIENTID="$BW_CLIENT_ID"
  export BW_CLIENTSECRET="$BW_CLIENT_SECRET"
  # Clear any stale session
  bw logout 2>/dev/null || true
  BW_SESSION=$(bw login --apikey 2>&1 | grep -oP 'export BW_SESSION="\K[^"]+' || true)
  if [[ -z "$BW_SESSION" ]]; then
    log_error "Failed to login to Bitwarden/Vaultwarden"
    return 1
  fi
  export BW_SESSION
  bw sync 2>&1 | tee -a "$LOGFILE"
  log_ok "Vaultwarden: authenticated and synced"
}

bw_get_item() {
  local item_name="$1"
  bw get item "$item_name" 2>/dev/null || bw list items --search "$item_name" 2>/dev/null | jq -r '.[0] // empty'
}

bw_get_field() {
  local item_json="$1"
  local field_name="$2"
  echo "$item_json" | jq -r --arg f "$field_name" '
    (.. | objects | select(.name == $f) // .fields[]? | select(.name == $f) | .value) // 
    (.login.password // .password // empty)
  ' 2>/dev/null || echo ""
}

bw_get_password() {
  local item_json="$1"
  echo "$item_json" | jq -r '.login.password // .password // ""' 2>/dev/null || echo ""
}

bw_update_password() {
  local item_name="$1"
  local new_password="$2"
  log_info "Updating password for Vaultwarden item: $item_name"
  local item_json
  item_json=$(bw get item "$item_name" 2>/dev/null || bw list items --search "$item_name" 2>/dev/null | jq -r '.[0]')
  if [[ -z "$item_json" || "$item_json" == "null" ]]; then
    log_error "Item '$item_name' not found in Vaultwarden"
    return 1
  fi
  local updated_json
  updated_json=$(echo "$item_json" | jq --arg p "$new_password" '.login.password = $p')
  local item_id
  item_id=$(echo "$item_json" | jq -r '.id')
  echo "$updated_json" | bw encode | bw edit item "$item_id" 2>&1 | tee -a "$LOGFILE"
  log_ok "Vaultwarden item '$item_name' updated"
}

bw_set_field() {
  local item_name="$1"
  local field_name="$2"
  local field_value="$3"
  log_info "Setting field '$field_name' on Vaultwarden item: $item_name"
  local item_json
  item_json=$(bw get item "$item_name" 2>/dev/null || bw list items --search "$item_name" 2>/dev/null | jq -r '.[0]')
  if [[ -z "$item_json" || "$item_json" == "null" ]]; then
    log_error "Item '$item_name' not found in Vaultwarden"
    return 1
  fi
  local updated_json
  updated_json=$(echo "$item_json" | jq --arg fn "$field_name" --arg fv "$field_value" '
    .fields = ((.fields // []) + [{"name": $fn, "value": $fv, "type": 0}])
  ')
  local item_id
  item_id=$(echo "$item_json" | jq -r '.id')
  echo "$updated_json" | bw encode | bw edit item "$item_id" 2>&1 | tee -a "$LOGFILE"
  log_ok "Field '$field_name' set on '$item_name'"
}

# ---- Rollback Support ----
ROLLBACK_FILE="${ROLLBACK_FILE:-/tmp/secret-rotation-rollback-$(date +%Y%m%d-%H%M%S).json}"

save_backup() {
  local service_name="$1"
  local old_value="$2"
  local field="$3"
  # Append to rollback file
  local entry
  entry=$(jq -n \
    --arg service "$service_name" \
    --arg field "$field" \
    --arg old "$old_value" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{service: $service, field: $field, old_value: $old, timestamp: $ts}')
  if [[ ! -f "$ROLLBACK_FILE" ]]; then
    echo "[]" > "$ROLLBACK_FILE"
  fi
  local tmp
  tmp=$(mktemp)
  jq --argjson e "$entry" '. += [$e]' "$ROLLBACK_FILE" > "$tmp" && mv "$tmp" "$ROLLBACK_FILE"
}

# ---- Health Check Helpers ----
check_url() {
  local url="$1"
  local expected_status="${2:-200}"
  local timeout="${3:-10}"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout "$timeout" --max-time 15 "$url" 2>/dev/null || echo "000")
  if [[ "$code" == "$expected_status" ]]; then
    log_ok "  Health: $url → $code"
    return 0
  else
    log_warn "  Health: $url → $code (expected $expected_status)"
    return 1
  fi
}

check_url_header() {
  local url="$1"
  local header="$2"
  local expected_status="${3:-200}"
  local timeout="${4:-10}"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "$header" --connect-timeout "$timeout" --max-time 15 "$url" 2>/dev/null || echo "000")
  if [[ "$code" == "$expected_status" ]]; then
    log_ok "  Health: $url (auth) → $code"
    return 0
  else
    log_warn "  Health: $url (auth) → $code (expected $expected_status)"
    return 1
  fi
}

# ---- Random Password Generator ----
generate_password() {
  local length="${1:-48}"
  # Generate a URL-safe base64 password (no +/ or =)
  openssl rand -base64 "$((length * 3 / 4 + 1))" | tr -d '+/=' | cut -c1-"$length" || \
  < /dev/urandom tr -dc 'A-Za-z0-9!@#$%^&*()_+-=' | head -c "$length"
}

generate_api_key() {
  # Netbird-style: nbp_<base64url>
  local prefix="${1:-nbp}"
  local rand
  rand=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
  echo "${prefix}_${rand}"
}
