#!/usr/bin/env bash
# Provisions Project NOMAD on a Debian/Ubuntu VM (ton-cluster side infra).
# Idempotent: re-running keeps .env (secrets) and existing data, only re-renders compose.yml.
#
# Usage (as root on the VM):
#   bash provision.sh https://nomad.lag0.com.br
#
# Layout on the host:
#   /opt/project-nomad/.env          -> generated secrets (chmod 600, never in git)
#   /opt/project-nomad/compose.yml   -> rendered from compose.yml.tmpl
#   /opt/project-nomad/storage       -> ZIM/models/notes (NOMAD_STORAGE_PATH)
#   /opt/project-nomad/{mysql,redis} -> database/queue state
set -euo pipefail

URL="${1:-https://nomad.lag0.com.br}"
BASE=/opt/project-nomad
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\n==> %s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker CE"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

mkdir -p "$BASE"/{storage,mysql,redis}

if [ ! -f "$BASE/.env" ]; then
  log "generating secrets in $BASE/.env"
  umask 077
  {
    echo "APP_KEY=$(openssl rand -hex 32)"
    echo "MYSQL_ROOT_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-24)"
    echo "DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-24)"
  } > "$BASE/.env"
  umask 022
fi

# shellcheck disable=SC1091
set -a; . "$BASE/.env"; set +a

log "rendering $BASE/compose.yml"
sed -e "s|__APP_KEY__|${APP_KEY}|g" \
    -e "s|__URL__|${URL}|g" \
    -e "s|__DB_PASSWORD__|${DB_PASSWORD}|g" \
    -e "s|__MYSQL_ROOT_PASSWORD__|${MYSQL_ROOT_PASSWORD}|g" \
    "$SCRIPT_DIR/compose.yml.tmpl" > "$BASE/compose.yml"

log "starting the stack"
cd "$BASE"
docker compose -f "$BASE/compose.yml" pull -q
docker compose -f "$BASE/compose.yml" up -d

log "waiting for the admin health endpoint"
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
    echo "admin healthy after ${i}0s"
    break
  fi
  sleep 10
done

docker compose -f "$BASE/compose.yml" ps
curl -fsS http://127.0.0.1:8080/api/health && echo
