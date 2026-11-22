# mail — Stalwart (lag0.com.br)

Servidor de e-mail do domínio `lag0.com.br`: **Stalwart v1.1.1** rodando no
`ton-cluster`, com a **borda de transporte na VPS `ton-holanda`** (que não tem
aplicação de e-mail nenhuma) e um **relay de saída no OKE** (a casa e a VPS têm
saída SMTP bloqueada; a OCI não).

## Arquitetura

```
Internet ──25/465/587/993/443──► ton-holanda (88.216.187.80)
                                  HAProxy TCP + PROXY protocol v2
                                        │
                                   overlay NetBird (100.82.43.230)
                                        │
                                  ┌─────▼─────────────────────────┐
                                  │ pod stalwart-0 (ton-cluster)   │
                                  │  · sidecar netbird (identidade)│
                                  │  · Stalwart: SMTP/IMAP/JMAP    │
                                  │  · RocksDB em local-path       │
                                  └─────┬─────────────────────────┘
                                        │ saída (MtaRoute "oci-relay")
                                  ┌─────▼─────────────────────────┐
                                  │ mail-relay-oci (OKE)           │
                                  │  Postfix 25 → internet         │
                                  │  egress público 129.148.42.122 │
                                  └───────────────────────────────┘
```

Por que assim:

- A VPS só carrega conexão: HAProxy em modo TCP, `send-proxy-v2`, sem fila, sem
  DKIM, sem caixa postal. Ela envia o header PROXY, então o Stalwart vê o **IP
  real do cliente** (essencial para score de spam e rate limit).
- O Stalwart aceita PROXY protocol **apenas** de `100.82.78.56/32` (a VPS).
- A saída não passa pela VPS: ela não tem egress 25/465/587 (só 2525). O relay
  no OKE tem egress 25 liberado e entrega direto.
- A entrega VPS→pod só existe nos portos liberados na policy NetBird
  `mail-edge-ingress` (25/465/587/993/443). Porta fora da policy = timeout
  silencioso, não erro de firewall.

## Estado atual (2026-11-22)

| Item | Valor |
|---|---|
| MX | `lag0.com.br` → `10 mail.lag0.com.br` |
| A | `mail.lag0.com.br` → `88.216.187.80` (DNS-only, sem proxy Cloudflare) |
| Conta | `antonio@lag0.com.br` (role Admin) — senha no secret `mail-accounts` |
| Aliases | `postmaster@` e `abuse@` (contas próprias, para DMARC/TLS-RPT) |
| SPF | `v=spf1 mx ip4:129.148.42.122 ~all` (softfail de propósito) |
| DKIM | selectors `v1-rsa-20261122` e `v1-ed25519-20261122` (gerados pelo servidor) |
| DMARC | `p=none`, `rua=mailto:postmaster@lag0.com.br` |
| WebUI | https://mail.lag0.com.br/admin |
| PTR | `88.216.187.80` → `mail.lag0.com.br` (FCrDNS confirmado, 22/11) |

## Bootstrap (feito uma vez, documentado para reconstrução)

O Stalwart v1 guarda a configuração no próprio DataStore, não em arquivo. O
`config.json` (ConfigMap) só diz onde mora o RocksDB. O caminho usado:

1. subir o StatefulSet com `STALWART_RECOVERY_MODE=1` e
   `STALWART_RECOVERY_ADMIN` vindo do secret `stalwart-bootstrap` (só HTTP 8080);
2. `kubectl port-forward svc/stalwart 8080:8080` e aplicar planos com
   `stalwart-cli apply --file plano.ndjson` (usuário `admin`);
3. **criar o `ClusterRole`** — sem ele nenhum listener sobe (o wizard criaria):
   `{"name":"default","listeners":{"@type":"EnableAll"},"tasks":{"@type":"EnableAll"}}`
4. remover as envs de recovery, reiniciar e trocar para a conta de admin real.

O schema de cada objeto vem do próprio servidor (`stalwart-cli describe <Tipo>`)
e fica em cache em `~/.cache/stalwart-cli/*/schema-*.json` — é a fonte de
verdade para encodings (Set = `{"membro": true}`, List = `{"0": ...}`, objeto
com variante = `"@type"`).

## Operação

```bash
export KUBECONFIG=~/.kube/config
K="kubectl --context admin@ton-cluster"
$K -n mail port-forward svc/stalwart 8080:8080 &
PW=$($K -n mail get secret mail-accounts -o jsonpath='{.data.antonio}' | base64 -d)
stalwart-cli --url http://127.0.0.1:8080 --user antonio --password "$PW" query QueuedMessage
stalwart-cli --url http://127.0.0.1:8080 --user antonio --password "$PW" get QueuedMessage <id>
$K -n mail logs stalwart-0 -c stalwart --tail=50        # tracer Stdout em debug
```

Criar conta nova (`plan.ndjson`):

```json
{"@type":"upsert","object":"Account","matchOn":["name","domainId"],"value":{"u1":{"@type":"User","name":"fulano","domainId":"b","credentials":{"0":{"@type":"Password","secret":"<senha>"}}}}}
```

## SSO com Pocket ID (WebUI)

A WebUI do Stalwart autentica pelo Pocket ID (`https://id.lag0.com.br`). O
Stalwart **não** é cliente OAuth próprio: ele valida o token que o IdP emitiu e
mapeia para a conta local (resource-server).

Configuração (toda no DataStore do Stalwart, não em arquivo):

| Objeto | Campo | Valor |
|---|---|---|
| `Directory` (`Oidc`) | `issuerUrl` | `https://id.lag0.com.br` |
| | `claimUsername` | `mail_username` (custom claim do Pocket ID) |
| | `acceptedAudiences` | `{"mail-webui": true}` |
| `Application` (WebUI) | `oauthClientId` | `mail-webui` |
| `Authentication` | `directoryId` | id do Directory acima |
| Pocket ID | client OIDC | id `mail-webui`, **public + PKCE S256**, `skipConsent`, restrito ao grupo `mail-users` |
| Pocket ID | API | resource `https://mail.lag0.com.br` com `userDelegatedAccess` no client |

Regras que custaram tempo:

- **`resource` é obrigatório existir no Pocket ID.** A WebUI manda
  `resource=https://<host>` (RFC 8707) e o Pocket ID rejeita com
  `invalid_request` qualquer resource não cadastrado em *Administration → APIs*
  e não autorizado ao client (`PUT /api/apis/<id>/clients/<client_id>`
  `{"userDelegatedAccess": true}`). Sem isso o consentimento nunca completa.
- **A conta é mapeada pelo endereço de e-mail do IdP.** Com o e-mail do Pocket
  ID diferente do endereço da caixa o login autentica e depois falha com
  `Account domain does not exist or has been disabled`, apontando o domínio do
  e-mail do IdP. Use um custom claim com o endereço da caixa
  (`PUT /api/custom-claims/user/<id>` — o corpo é um **array** e substitui a
  lista inteira; `email_verified` é chave reservada e dá 400).
- **`oauthClientId` e `directoryId` andam juntos.** Com `oauthClientId` setado e
  `directoryId` nulo o login interno responde `Unknown client id` (o servidor
  OAuth do Stalwart não conhece o client) e o admin fica inacessível.
- **O Directory só recarrega com restart.** Mudou `Directory`/`Application`/
  `Authentication`? `kubectl -n mail delete pod stalwart-0`. Antes do restart o
  sintoma é token novo sendo recusado (`Failed to decode token`).
- **As primeiras tentativas após o restart falham** no fetch do UserInfo
  (`Network error: UserInfo request failed`) e estabilizam em segundos — não é
  configuração errada.
- Provisionamento: a conta precisa existir no Stalwart antes do 1º login (JIT
  criaria a conta, mas o endereço já é a caixa real aqui).

Apps que casam usuário por e-mail foram realinhados quando o e-mail do Pocket ID
passou a ser `antonio@lag0.com.br`: Immich (`user.email`) e Vaultwarden
(`users.email`), via SQL; Forgejo via `PATCH /api/v1/admin/users/<user>`.

## Pitfalls (custaram tempo)


- **ClusterRole ausente = zero listeners**, mesmo com `NetworkListener` criado.
- **Clientes IMAP/SMTP pecam contra o certificado**: use o hostname
  `mail.lag0.com.br`, nunca o IP do overlay (o certificado wildcard não cobre IP).
- **HAProxy com health check em porta implicit-TLS** derruba o backend: o
  servidor espera o ClientHello e o check estoura (Layer4 timeout). Nesses
  backends não há `check` de propósito.
- **Backend HTTPS sem PROXY protocol = o edge é banido pelo próprio servidor.**
  O Stalwart bane IP por varredura (`security.scan-ban`): um bot pedindo
  `/phpinfo` em 443 fez ele banir `100.82.78.56` (a VPS) por
  "Excessive port scanning attempts", e a partir daí **toda** conexão HTTPS
  morria com 0 bytes — o browser mostrava *"conexão recusada"* enquanto o TCP
  abria normalmente. `send-proxy-v2` é obrigatório em **todos** os backends, e
  cada `NetworkListener` precisa de `overrideProxyTrustedNetworks =
  {"100.82.78.56": true}`. O listener `https` nasceu com esse campo vazio (os
  outros quatro tinham), então todo cliente virava 100.82.78.56.
  Config do edge versionado em `mail/edge/haproxy.cfg`.
- **`BlockedIp` não some com o delete.** Apagar o objeto pela API zera a lista,
  mas o ban continua ativo em memória até reiniciar o container
  (`kubectl -n mail delete pod stalwart-0`) — a lista persistida fica no RocksDB
  e ele recomputa na subida.
- **Porta nova exige atualizar a policy NetBird** antes de culpar o HAProxy.
- `pkill -f "<padrão>"` por SSH mata a própria sessão quando o padrão aparece na
  linha de comando — use `pkill -x`.
- O resolver da VPS aponta para o próprio NetBird e falha de forma intermitente;
  não coloque MTA lá (não colocamos).
- Verificadores antigos dão `permerror` na assinatura Ed25519 (port25 faz isso).
  O RSA passa e o DMARC alinha; não é problema, mas não estranhe no relatório.

## Pendências conhecidas

- **PTR** do IP da borda (`88.216.187.80` → `mail.lag0.com.br`): autoatendimento
  no portal Cherry (Management IPs → engrenagem → Edit → PTR record). Sem isso,
  verificadores reportam `reverse lookup failed (NXDOMAIN)`.
- **Relay comercial** (Brevo/SMTP2GO/Postmark): hoje a saída depende do IP da
  OCI (129.148.42.122), que não tem PTR próprio. Trocar quando houver conta:
  `MtaRoute` tipo Relay com host/porta/credenciais do provedor e SPF
  `include:` do provedor no lugar do `ip4:`.
- **Backup** do PVC `data-stalwart-0` (RocksDB + mensagens) — ainda sem rotina.
- **MTA-STS / TLS-RPT** depois que o PTR estiver correto.
