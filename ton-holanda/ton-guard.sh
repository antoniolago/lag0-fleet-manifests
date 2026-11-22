#!/usr/bin/env bash
# Recarrega a tabela nft ton_guard (allowlist do node_exporter).
set -euo pipefail
nft delete table inet ton_guard 2>/dev/null || true
nft -f /etc/ton-guard.nft
