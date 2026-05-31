#!/usr/bin/env bash
# run-all.sh — Orchestrates Lag0 Secret Rotation (safe 2-phase)
# Usage:
#   --preflight    Test everything without changing anything
#   (no flags)     Create new credentials, verify, write to VW
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

MODE="${1:-}"
if [[ "$MODE" == "--preflight" ]]; then
  log_info "=== SAFE MODE: PREFLIGHT (read-only) ==="
  log_info "This run will NOT change any secrets"
else
  log_info "=== SAFE MODE: ROTATION ==="
  log_info "This run WILL create new credentials and write to Vaultwarden"
  log_info "Old credentials will NOT be revoked (overlap = 10 days)"
fi
echo ""

EXIT_CODE=0

log_info "PHASE 0: Login to Vaultwarden"
bw_login || { log_error "FATAL: Cannot login to Vaultwarden"; exit 1; }

for module in cloudflare netbird github harbor; do
  echo ""
  log_info "======================================"
  log_info "  MODULE: $module"
  log_info "======================================"
  if source "$SCRIPT_DIR/rotate-${module}.sh" && "rotate_${module}" "$MODE"; then
    log_ok "  Module $module: PASSED"
  else
    log_error "  Module $module: FAILED"
    EXIT_CODE=1
  fi
done

echo ""
if [[ "$EXIT_CODE" == "0" ]]; then
  if [[ "$MODE" == "--preflight" ]]; then
    log_ok "ALL PREFLIGHT CHECKS PASSED — safe to run rotation"
  else
    log_ok "ALL ROTATIONS COMPLETE"
    log_info "Next run will clean up credentials from this cycle"
  fi
else
  log_error "SOME MODULES FAILED"
  log_info "  Old credentials still work — zero damage"
  log_info "  Log: $LOGFILE"
fi
exit $EXIT_CODE
