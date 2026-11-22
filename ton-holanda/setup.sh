#!/usr/bin/env bash
# Instala/atualiza a coleta de métricas da ton-holanda.
# Idempotente: pode rodar de novo depois de editar qualquer arquivo.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
NB_USER="prometheus"

echo "== 1. diretórios e binário do exporter"
install -d -m 0755 /var/lib/node_exporter
install -m 0755 "$SRC/ton-traffic-exporter.py" /usr/local/bin/ton-traffic-exporter
chown -R root:"$NB_USER" /var/lib/node_exporter
chmod 0755 /var/lib/node_exporter

echo "== 2. configuração de cota (mantém valor existente)"
if [[ ! -f /etc/ton-traffic.conf ]]; then
  install -m 0644 "$SRC/ton-traffic.conf" /etc/ton-traffic.conf
fi

echo "== 3. TLS autoassinado do node_exporter"
install -d -m 0755 /etc/prometheus-node-exporter
if [[ ! -s /etc/prometheus-node-exporter/server.crt ]]; then
  openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout /etc/prometheus-node-exporter/server.key \
    -out /etc/prometheus-node-exporter/server.crt \
    -subj "/CN=ton-holanda.lag0.com.br" \
    -addext "subjectAltName=DNS:ton-holanda.netbird.lag0.com.br,IP:88.216.187.80,IP:100.82.78.56" >/dev/null 2>&1
fi
chown root:"$NB_USER" /etc/prometheus-node-exporter/server.key /etc/prometheus-node-exporter/server.crt
chmod 0640 /etc/prometheus-node-exporter/server.key
chmod 0644 /etc/prometheus-node-exporter/server.crt
install -m 0644 "$SRC/node-exporter-web.yml" /etc/prometheus-node-exporter/web.yml

echo "== 4. flags do node_exporter"
if (prometheus-node-exporter --help 2>&1 || true) | grep -qF -- '--collector.disable-defaults'; then
  COLLECTORS="--collector.disable-defaults --collector.textfile --collector.netdev --collector.uname --web.disable-exporter-metrics"
else
  echo "ERRO: node_exporter sem --collector.disable-defaults; abortando para não publicar 200 KB por raspagem" >&2
  exit 1
fi
cat >/etc/default/prometheus-node-exporter <<EOF
# Coleta enxuta: só rede + métricas próprias (textfile).
# Payload pequeno porque a raspagem atravessa a internet.
ARGS="$COLLECTORS --collector.textfile.directory=/var/lib/node_exporter --web.listen-address=:9100 --web.config.file=/etc/prometheus-node-exporter/web.yml"
EOF
systemctl daemon-reload
systemctl enable --now prometheus-node-exporter >/dev/null 2>&1 || true
systemctl restart prometheus-node-exporter

echo "== 5. guarda de firewall (só a rede de casa e o CGNAT do NetBird leem :9100)"
install -m 0644 "$SRC/ton-guard.nft" /etc/ton-guard.nft
install -m 0755 "$SRC/ton-guard.sh" /usr/local/bin/ton-guard.sh
install -m 0644 "$SRC/ton-guard.service" /etc/systemd/system/ton-guard.service
systemctl daemon-reload
systemctl enable ton-guard >/dev/null 2>&1 || true
systemctl restart ton-guard

echo "== 6. coletor periódico"
install -m 0644 "$SRC/ton-traffic-exporter.service" /etc/systemd/system/ton-traffic-exporter.service
install -m 0644 "$SRC/ton-traffic-exporter.timer" /etc/systemd/system/ton-traffic-exporter.timer
systemctl daemon-reload
systemctl enable --now ton-traffic-exporter.timer >/dev/null 2>&1 || true
systemctl start ton-traffic-exporter.service

echo "== 7. vnstat (acumulado diário/mensal persistente)"
systemctl enable --now vnstat >/dev/null 2>&1 || true
systemctl restart vnstat

echo "== 8. verificação"
sleep 2
systemctl is-active prometheus-node-exporter ton-traffic-exporter.timer vnstat ton-guard | tr '\n' ' '; echo
curl -sk https://127.0.0.1:9100/metrics | grep -c '^ton_holanda_' | sed 's/^/ton_holanda_* séries: /'
curl -sk https://127.0.0.1:9100/metrics | grep -E '^node_network_receive_bytes_total\{device="(eth0|wt0)"' || true
