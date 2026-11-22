# Monitoração da VPS ton-holanda

A ton-holanda (`88.216.187.80`, NetBird `100.82.78.56`) é **exit node do NetBird** e
borda de mail (haproxy 25/465/587/993/443 → Stalwart no OKE). O plano do provedor tem
cota de tráfego, então precisamos saber **quanto** já foi e **quem** consumiu.

## O que roda na VPS

| Componente | Papel |
|---|---|
| `prometheus-node-exporter` | expõe `:9100` com apenas os coletores `netdev` + `textfile` (~14 KB por raspagem, sem métricas de Go/runtime) |
| `ton-traffic-exporter.timer` | a cada 30 s escreve `/var/lib/node_exporter/ton_traffic.prom` |
| `vnstat` | acumulado diário/mensal do `eth0` em SQLite (imune a reboot e à retenção do Prometheus) |
| `ton-guard.service` | tabela nft `inet ton_guard` que libera `:9100` só para a rede de casa e o CGNAT do NetBird |
| TLS autoassinado | `/etc/prometheus-node-exporter/{server.crt,server.key}`; o Prometheus raspa com `insecure_skip_verify` |

### Métricas publicadas (`ton_holanda_*`)

- `peer_rx_bytes{peer,ip}` / `peer_tx_bytes{peer,ip}` — contadores do WireGuard do kernel por peer.
  `tx` = o que a VPS **entregou** ao peer (download dele pelo exit node); `rx` = o que ele **enviou**.
- `peer_info{peer,ip,state,connection}` — metadados (estado e caminho P2P/relay), separados dos
  contadores de propósito: labels voláteis dentro de um contador criam séries novas a cada
  reconexão e zeram o `increase()`.
- `traffic_month_*`, `traffic_day_*`, `traffic_history_bytes{date,direction}`, `traffic_total_*` — vnstat.
- `iface_since_boot_bytes{direction}` — `/proc/net/dev` do `eth0` (conferência contra o painel do provedor).
- `quota_bytes`, `peers_active`, `month_info`, `exporter_last_run_seconds`.

## Como (re)instalar

```bash
scp -r . root@88.216.187.80:/tmp/tonmon
ssh root@88.216.187.80 'bash /tmp/tonmon/setup.sh'
```

O script é idempotente. Ele **não** sobrescreve `/etc/ton-traffic.conf` se já existir.

## Cota

```bash
# na VPS: valor em bytes (ex.: 50 GiB = 53687091200)
sed -i 's/^TON_QUOTA_BYTES=.*/TON_QUOTA_BYTES=53687091200/' /etc/ton-traffic.conf
systemctl start ton-traffic-exporter.service
```

Sem `TON_QUOTA_BYTES`, o dashboard usa a variável `quota_gb` (padrão 1000 GB).

## Allowlist do `:9100`

`/etc/ton-guard.nft` tem o set `trusted` com o IP público da casa (`189.6.244.241`).
Se o IP mudar, edite o set e rode `systemctl reload ton-guard`.
O CGNAT do NetBird (`100.82.0.0/16`) continua liberado para diagnóstico pelo túnel.

## Lado Prometheus/Grafana (neste repo)

- `kube-prometheus-stack-ton/helm.yaml` → job `ton-holanda` (`scheme: https`, `scrape_interval: 120s`).
  O intervalo é 2 min de propósito: cada raspagem custa ~14 KB de **egress** da própria VPS.
- `kube-prometheus-stack-ton/gen_dashboards.py` → dashboard `lag0-holanda`
  ("VPS ton-holanda · Tráfego, Cota & Quem Usou"), provisionado pelo ConfigMap `lag0-dashboards`.

Depois de mexer no dashboard: `python3 gen_dashboards.py` e `kubectl apply -k kube-prometheus-stack-ton`.

## Limites honestos

- O `eth0` mistura exit node + proxy de mail + SSH. A separação sai da comparação entre
  `wt0` (túnel) e `eth0`: a diferença é tráfego que não é exit node.
- Se o `netbird` reiniciar, os contadores do WireGuard voltam a zero; o histórico diário do
  vnstat continua válido.
- O vnstat passou a contar na instalação — o que veio antes só existe nos contadores do `/proc/net/dev`
  (que zeram em reboot) e no painel do provedor.
