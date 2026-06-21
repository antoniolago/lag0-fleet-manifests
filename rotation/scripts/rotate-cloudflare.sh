#!/usr/bin/env bash
# rotate-cloudflare.sh — Rotates Cloudflare API Token for cert-manager
# Bootstrap config needs: CLOUDFLARE_BOOTSTRAP_TOKEN, CLOUDFLARE_ZONE_ID
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

CF_API="https://api.cloudflare.com/client/v4"
CF_TNAME="${CLOUDFLARE_TOKEN_NAME:-lag0-cert-manager}"

rotate_cloudflare() {
  log_info "=== Cloudflare API Token Rotation ==="

  local bt="${CLOUDFLARE_BOOTSTRAP_TOKEN:-}"
  local zi="${CLOUDFLARE_ZONE_ID:-}"
  if [[ -z "$bt" ]]; then
    log_error "CLOUDFLARE_BOOTSTRAP_TOKEN not set in config"
    return 1
  fi
  if [[ -z "$zi" ]]; then
    log_error "CLOUDFLARE_ZONE_ID not set in config"
    return 1
  fi

  local auth tname
  auth=(-H "Authorization: Bearer $bt" -H "Content-Type: application/json")
  tname="$CF_TNAME"

  log_info "STEP 1: Listing existing tokens..."
  local existing
  existing=$(curl -sf "${CF_API}/user/tokens" "${auth[@]}" 2>/dev/null | jq -c '.result[] // empty') || {
    log_error "Failed: cannot list Cloudflare tokens (check bootstrap permissions)"
    return 1
  }
  log_ok "Listed tokens successfully"

  local oid oval
  oid=$(echo "$existing" | jq -r --arg n "$tname" 'select(.name == $n) | .id // empty')
  oval=$(echo "$existing" | jq -r --arg n "$tname" 'select(.name == $n) | .value // empty')

  if [[ -n "$oid" ]]; then
    log_info "Found existing token: $oid"
  else
    log_warn "No token named $tname found, will create fresh"
  fi

  log_info "STEP 2: Determining token permissions..."
  local perms
  if [[ -n "$oid" ]]; then
    perms=$(curl -sf "${CF_API}/user/tokens/${oid}" "${auth[@]}" | jq '.result.policies')
    log_ok "Permissions cloned from existing token"
  else
    perms=$(jq -n --arg z "$zi" '[{effect:"allow",resources:{("com.cloudflare.api.account.zone."+$z):"*"},permission_groups:[{id:"04e9aedc0e3ff5d0b4d1a2d1d0f0e0e0",name:"DNS"},{id:"f001c0f0a0e0d0c0b0a0908070605040",name:"Zone Read"}]}]')
    log_ok "Using default DNS:Edit + Zone:Read permissions"
  fi

  log_info "STEP 3: Creating new token..."
  local nname="${tname}-$(date +%Y%m%d)"
  log_info "Creating: $nname"
  local npayload=$(jq -n --arg n "$nname" --argjson p "$perms" '{name:$n,policies:$p}')
  local nresult=$(curl -sf -X POST "${CF_API}/user/tokens" "${auth[@]}" -d "$npayload" 2>/dev/null) || {
    log_error "FAILED: could not create new token"
    return 1
  }
  local nid ntv
  nid=$(echo "$nresult" | jq -r '.result.id // empty')
  ntv=$(echo "$nresult" | jq -r '.result.value // empty')
  if [[ -z "$nid" || -z "$ntv" ]]; then
    log_error "FAILED: token created but value not returned"
    return 1
  fi
  log_ok "New token created: $nname ($nid)"
  if [[ -n "$oval" ]]; then
    save_backup "cloudflare-api-token" "$oval" "cloudflare-token"
    log_ok "Old token backed up"
  fi

  log_info "STEP 4: Writing new token to Vaultwarden..."
  bw_update_password "cloudflare-secrets" "$ntv" && log_ok "Vaultwarden updated" || log_warn "Vaultwarden item not found"

  log_info "STEP 5: Verifying new token..."
  log_info "  Waiting 30s for VKS sync..."
  sleep 30
  local vr=$(curl -sf "${CF_API}/user/tokens/verify" -H "Authorization: Bearer $ntv" 2>/dev/null)
  if echo "$vr" | jq -e ".success == true" >/dev/null 2>&1; then
    log_ok "VERIFIED: new token works!"
  else
    log_error "VERIFICATION FAILED: new token does not work!"
    log_error "ABORTING: old token NOT revoked (keeping existing credentials)"
    return 1
  fi

  log_info "STEP 6: Saving fingerprints for next cycle cleanup..."
  save_fingerprint "cloudflare" "$nid" "$nname"
  log_ok "Fingerprint saved for ${nname} (${nid})"
  log_info "  Old token NOT revoked — 10-day overlap window active"
  log_info "  Next cycle will clean up this cycle's old credentials"

  log_info "=== Cloudflare API Token Rotation Complete ==="
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  bw_login
  rotate_cloudflare
fi
