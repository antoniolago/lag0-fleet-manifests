# mail.lag0.com.br — Stalwart na OCI (24/7)

O Stalwart roda **no cluster OKE** (`oci-lag0`) porque a casa pode cair; a borda continua
na VPS `ton-holanda`, que é o único ponto com a porta 25 de entrada liberada.

```
                 MX (25) / 443 / 465 / 587 / 993
internet ────────────────────────────────────────► ton-holanda (88.216.187.80)
                  HAProxy, send-proxy-v2                  │
                                                          │ WireGuard (NetBird, 100.82.0.0/16)
                                                          ▼
                                          pow/stalwart-0  100.82.211.101  (OCI)
                                            listener https/smtp/imaps... com PROXY v2
                                            DataStore RocksDB em /var/lib/stalwart (hostPath)
relay de saída: direto para o MX do destinatário (egress 25 do OKE é liberado)
```

## O que depende de quê

- **Entrada**: `ton-holanda:25` é o MX. Sem PROXY protocol em todos os backends/listeners
  o Stalwart vê o IP do edge, bane por scan e derruba o HTTPS (ver `mail/README.md`).
- **NetBird é obrigatório**: o edge alcança o pod pelo overlay (`vps-istio` → grupo
  `mail-edge`). O peer tem IP fixo (`100.82.211.101`) e o HAProxy aponta para ele —
  se o peer mudar de IP, o mail para.
- **SSO**: Directory `Oidc` para `id.lag0.com.br` (Pocket ID). Se o Pocket ID (na casa)
  cair, o login da WebUI e do IMAP/SMTP caem junto.
- **Storage**: `hostPath /var/lib/stalwart` no nó único. **Não usar oci-bv**: o block
  volume mínimo é 50 GB e custa por GB.

## Limitações conhecidas

- **PTR (rDNS) não é configurável**: o IP de saída do cluster pertence a um NAT Gateway
  da OCI e a API recusa (`Cannot update public IP assigned to an entity of type
  NAT_GATEWAY`). O SPF já autoriza `ip4:129.148.42.122`. Sem PTR, Gmail/Outlook podem
  classificar como spam; o caminho correto é um smarthost com PTR próprio.
- **Backup para o rustfs ainda não está ativo**: o backup roda local
  (`/var/backups/stalwart`, 6/6h, retenção de 7 dias). O rustfs só é alcançável pela
  LAN da casa, a rota de subnet não é instalada no peer do overlay, e a publicação via
  túnel exige permissão de Zero Trust no token do Cloudflare.

## Backup

`backup.yaml` — CronJob a cada 6h: `tar czf` do DataStore com retenção de 28 cópias.
Para restaurar: `tar xzf` no hostPath e reiniciar o StatefulSet.

## DR (volta para a casa)

O StatefulSet em `mail/` (ton-cluster) ficou em `replicas: 0` com o DataStore antigo.
Para voltar: exportar o DataStore da OCI (tar), aplicar no PVC `data-stalwart-0`,
`scale --replicas=1` e apontar o HAProxy de volta para o peer da casa.

## Manifests

- `namespace.yaml`, `configmap.yaml`, `service.yaml`, `statefulset.yaml`, `backup.yaml`
- `kustomization.yaml` (aplicar com `kubectl --context oci-lag0 apply -k mail-oci/`)
- Segredos vivem fora do repo: `netbird-setup` (setup key com auto_group `mail-edge`).
