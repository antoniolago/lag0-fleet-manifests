#!/usr/bin/env bash
# run-all.sh — Orchestrates all rotation scripts
# Runs every 10 days via Hermes cronjob
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

log_info "============================================="
log_info "  LAG0 SECRET ROTATION SUITE — $(date)"
log_info "============================================="

EXIT_CODE=0
log_info "PHASE 0: Login to Vaultwarden"
bw_login || { log_error "FATAL: Cannot login to Vaultwarden"; exit 1; }

for phase in cloudflare netbird github harbor; do
  log_info ""
  log_info "=== PHASE: $phase ==="
  if source "$SCRIPT_DIR/rotate-${phase}.sh" && "rotate_${phase}"; then
    log_ok "Phase $phase: SUCCESS"
  else
    log_error "Phase $phase: FAILED"
    EXIT_CODE=1
  fi
done

log_info ""
log_info "============================================="
if [[ "$EXIT_CODE" == "0" ]]; then
  log_info "  ALL ROTATIONS COMPLETE"
else
  log_error "  SOME ROTATIONS FAILED (check logs)"
  log_info "  Rollback file: $ROLLBACK_FILE"
  log_info "  Log file: $LOGFILE"
fi
log_info "============================================="
exit $EXIT_CODE
