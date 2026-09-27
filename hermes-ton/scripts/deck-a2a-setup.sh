#!/usr/bin/env bash
# ── Steam Deck: turn its Hermes runtime into an A2A agent of the fleet ─────────
#
# Roda NO Steam Deck (Modo Desktop, Konsole). Idempotente — pode repetir.
#
# O que ele faz:
#   1. grava no ~/.hermes/.env o que faz o servidor A2A nascer alcançável
#      (A2A_HOST=0.0.0.0) em vez de só em loopback, com o nome/path que o hub usa;
#   2. põe os tokens: os que o Deck ACEITA (A2A_PEER_TOKENS) e o token próprio do
#      Deck (A2A_TOKEN_STEAMDECK);
#   3. garante o gateway rodando como serviço systemd de usuário
#      (`hermes gateway install` / `restart`);
#   4. confere e imprime o resultado (porta 9900, Agent Card, IPs).
#
# Uso (os valores vêm do Vaultwarden, item `hermes-a2a` — nunca por chat):
#   bash deck-a2a-setup.sh \
#     --accept "ton-desktop:<A2A_TOKEN_TON_DESKTOP>,ton-cluster:<A2A_TOKEN_TON_CLUSTER>" \
#     --own    "<A2A_TOKEN_STEAMDECK>"
#
# Sem argumentos ele só INSPECIONA (dry-run) e diz o que falta.
set -uo pipefail
ENV_FILE="$HOME/.hermes/.env"
ACCEPT=""; OWN=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --accept) ACCEPT="${2:-}"; shift 2;;
    --own)    OWN="${2:-}";    shift 2;;
    --dry-run) DRY=1; shift;;
    *) echo "argumento desconhecido: $1"; exit 2;;
  esac
done

echo "== Steam Deck · A2A =="
echo "  host=$(hostname) user=$(whoami) home=$HOME"

echo
echo "-- runtime --"
HERMES_BIN="$(command -v hermes || true)"
if [ -z "$HERMES_BIN" ] && [ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]; then
  HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/hermes"
fi
if [ -z "$HERMES_BIN" ]; then
  echo "  ERRO: não achei o binário \`hermes\` (nem no PATH, nem em ~/.hermes/hermes-agent/venv/bin)."
  echo "  No Deck, instale o runtime antes: o app desktop só é cliente."
  exit 1
fi
echo "  binário: $HERMES_BIN"
"$HERMES_BIN" --version 2>/dev/null | head -1 | sed 's/^/  versão: /'

echo
echo "-- estado atual --"
[ -f "$ENV_FILE" ] && echo "  .env: existe ($(grep -c . "$ENV_FILE") linhas)" || echo "  .env: ainda não existe"
for k in A2A_HOST A2A_PORT A2A_AGENT_NAME A2A_PUBLIC_URL; do
  v=$(grep -m1 "^$k=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
  echo "  $k=${v:-<unset>}"
done
for k in A2A_PEER_TOKENS A2A_TOKEN_STEAMDECK; do
  v=$(grep -m1 "^$k=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
  if [ -n "$v" ]; then
    n=$(echo "$v" | awk -F, '{print NF}')
    echo "  $k=<definido: $n entradas, ${#v} chars>"
  else
    echo "  $k=<unset>"
  fi
done
echo "  porta 9900: $(ss -lnt 2>/dev/null | grep -q ':9900' && ss -lnt | grep ':9900' | awk '{print $4}' | head -1 || echo 'nada escutando')"
echo "  netbird: $(command -v netbird >/dev/null 2>&1 && (netbird status 2>/dev/null | grep -m1 -E 'Status|NetBird IP' || echo instalado) || echo 'não instalado (opcional: dá acesso fora de casa)')"

if [ "$DRY" = 1 ] || [ -z "$ACCEPT" ] || [ -z "$OWN" ]; then
  echo
  echo "-- dry-run: nada alterado --"
  echo "  pra aplicar, repita com --accept e --own (valores do item hermes-a2a no Vaultwarden)."
  exit 0
fi

echo
echo "-- aplicando --"
mkdir -p "$HOME/.hermes"
[ -f "$ENV_FILE" ] && cp -a "$ENV_FILE" "$ENV_FILE.bak-$(date +%Y%m%d-%H%M%S)" && echo "  backup: $ENV_FILE.bak-$(date +%Y%m%d-%H%M%S)"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
upsert() { # key value
  local k="$1" v="$2"
  if grep -q "^$k=" "$ENV_FILE" 2>/dev/null; then
    python3 - "$ENV_FILE" "$k" "$v" <<'PY'
import sys
path, k, v = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().splitlines()
out, seen = [], False
for ln in lines:
    if ln.startswith(k + "="):
        if not seen:
            out.append(f"{k}={v}"); seen = True
    else:
        out.append(ln)
open(path, "w").write("\n".join(out) + "\n")
PY
  else
    printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
  fi
}
upsert A2A_HOST 0.0.0.0
upsert A2A_PORT 9900
upsert A2A_AGENT_NAME steamdeck
upsert A2A_PUBLIC_URL "https://hermes.lag0.com.br/a2a/deck"
upsert A2A_PEER_TOKENS "$ACCEPT"
upsert A2A_TOKEN_STEAMDECK "$OWN"
echo "  .env atualizado ($(grep -c . "$ENV_FILE") linhas; tokens não são impressos)"
grep -oE '^A2A_(HOST|PORT|AGENT_NAME|PUBLIC_URL)=.*' "$ENV_FILE" | sed 's/^/  /'

echo
echo "-- serviço --"
if systemctl --user list-unit-files 2>/dev/null | grep -q 'hermes-gateway'; then
  echo "  unit já existe -> restart"
  "$HERMES_BIN" gateway restart 2>&1 | tail -3 | sed 's/^/  /'
else
  echo "  instalando serviço de usuário"
  "$HERMES_BIN" gateway install 2>&1 | tail -5 | sed 's/^/  /'
fi
sleep 5

echo
echo "-- verificação --"
echo "  gateway: $("$HERMES_BIN" gateway status 2>&1 | head -3 | tr '\n' ' ')"
L=$(ss -lnt 2>/dev/null | grep ':9900' | awk '{print $4}' | head -1)
echo "  listen 9900: ${L:-nada}  (esperado: 0.0.0.0:9900)"
if [ -n "$L" ]; then
  echo "  agent card local:"; curl -s -m 5 http://127.0.0.1:9900/.well-known/agent-card.json 2>/dev/null | head -c 200 | sed 's/^/    /'; echo
else
  echo "  !! nada escutando: veja ~/.hermes/logs/gateway.log (e, se o app desktop estiver em modo local, ele pode estar disputando a 9900)"
fi
echo "  IPs: LAN=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | grep -v '^100\.' | cut -d/ -f1 | head -1) netbird=$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | grep '^100\.' | cut -d/ -f1 | head -1)"
echo
echo "== pronto: o hub publica este Deck em https://hermes.lag0.com.br/a2a/deck =="
