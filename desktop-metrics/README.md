# desktop-metrics — exporter do host (IPFIX + NetBird)

Prometheus exporter que roda **na ton-desktop** (não no cluster) e publica duas
fontes que não existem dentro do Kubernetes:

| Família | Fonte | Uso |
|---|---|---|
| `lag0_flow_*` | IPFIX do MikroTik → `nfcapd` em `~/flows` | dashboards de tráfego da rede da casa |
| `lag0_netbird_*` / `lag0_wg_*` | `netbird status -j` (pod `casa-router`) e `wg show` (pod `wg-client`) | dashboard de peers e túneis NetBird |

Endpoint: `http://192.168.88.108:9101/metrics` (scrape do Prometheus no
`kube-prometheus-stack`, job `lag0-exporter`, a cada 60 s).

## Instalação (ton-desktop)

```bash
mkdir -p ~/.local/bin
cp lag0-metrics.py ~/.local/bin/ && chmod +x ~/.local/bin/lag0-metrics.py
cp lag0-metrics.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lag0-metrics.service
curl -s localhost:9101/metrics | head
```

Depende de `nfdump` (pacote `nfdump`) e do `nfcapd` já coletando em `~/flows`.

## Semântica das métricas de fluxo

- Tudo em `lag0_flow_*` é **gauge de bytes por janela** (300 s). bps =
  `valor * 8 / 300` — é assim que os painéis calculam.
- O RouterOS exporta a saída com o IP da LAN e o retorno **pós-NAT**
  (`192.168.0.2`). O exporter casa a tupla invertida
  `(proto, ip remoto, porta do serviço, porta local)` com a saída do host
  interno, então o download aparece atribuído ao dispositivo certo.
- `lag0_flow_unattributed_bytes` é o retorno sem saída correspondente na
  janela (fluxo começou antes). Não é erro.
- Cardinalidade limitada a 250 séries por família; o resto vai para `other`.

## Semântica das métricas do NetBird

- `lag0_netbird_peer_transfer_bytes{peer,direction}` é **counter** (cumulativo
  do peer) → use `rate()`.
- `lag0_netbird_peer_latency_seconds`, `..._handshake_age_seconds` e
  `..._peer_connected` são gauges.
- `lag0_wg_*` vem do `wg show` do túnel ton-cluster ↔ OKE.

## Pitfalls

- O pod `casa-router` só enxerga os peers que ele conhece; se um peer não
  aparece, é porque o cliente não está no mesmo network/rota.
- `kubectl exec` a cada 30 s é cacheado em memória (25 s para NetBird, 55 s
  para flows); scrape mais frequente que isso só repete o cache.
- Se a desktop desliga, o dashboard de tráfego fica sem dados (o `nfcapd`
  também mora lá). O `up` do job `lag0-exporter` no Prometheus denuncia.
