# netbird-internal-dns — visão interna de `*.lag0.com.br`

Todo subdomínio de `lag0.com.br` que o Istio do **ton-cluster** serve tem de
abrir **de dentro da malha NetBird**, inclusive de peers fora da LAN
(`ton-holanda`, celular no 4G, notebook em viagem). Isso exige duas coisas ao
mesmo tempo — DNS e rota:

| Camada | Onde vive | O que faz |
|---|---|---|
| DNS (visão interna) | **MikroTik** `192.168.88.1` → `/ip/dns/static` | `host.lag0.com.br` → `CNAME istio-ton.lag0.com.br` (`A 192.168.88.190`) |
| DNS (resolvedor do mesh) | Technitium `192.168.88.191` / peer `100.82.25.208` | zona forwarder `lag0.com.br` → `192.168.88.1`; catch-all dos peers |
| Rota | NetBird | network `istio-ton` com resource host `192.168.88.190/32`, router no grupo `casa-routers`, policy `istio-interno` (`sources: All`) |

`192.168.88.190` é o VIP LoadBalancer do Istio do ton-cluster, com certificado
`*.lag0.com.br` (Let's Encrypt) e gateway `*.lag0.com.br` — por isso **um único
IP cobre todos os subdomínios** e não é preciso expor nada na internet (a casa
está atrás de CGNAT).

## Fluxo de uma requisição

```
peer (100.82.x) --DNS--> Technitium 100.82.25.208 --forward--> MikroTik .1
                                                   └-- CNAME --> istio-ton.lag0.com.br (192.168.88.190)
peer --TCP 443--> wt0 --rota istio-vip /32--> casa-router (pod no ton-cluster) --> Istio VIP .190 --> service
```

## Exceções (não são CNAME para o istio-ton)

- **`nb.lag0.com.br`** continua **público** (`istio-oke` → NLB do OKE). É a URL
  de management que um peer novo usa para se matricular; se ela dependesse da
  rota interna, o peer sem network map não conseguiria nem entrar. Não mover.
- **`grafana.lag0.com.br`** → `CNAME istio-oke.lag0.com.br`. O Grafana roda no
  OKE (`monitoring`); o VS no ton-cluster devolve 503.
- Nomes que apontam para host da LAN (`rd.lag0.com.br` → `192.168.88.194`) não
  são servidos pelo gateway e exigem rota de LAN, não o VIP.

## Arquivos

- `gen-records.sh` — gera `records.txt` a partir dos VirtualServices do
  contexto `admin@ton-cluster` (o gateway é a fonte de verdade; não editar o
  txt à mão).
- `records.txt` — estado desejado, um `host cname` por linha.
- `sync.py` — reconcilia o MikroTik com `records.txt`. **Dry-run por padrão**;
  `--apply` escreve e faz flush do cache DNS do roteador; `--list` mostra o
  estado atual; `--prune` remove registros `*.lag0.com.br` fora do arquivo
  (por padrão só reporta).

```bash
export KUBECONFIG=~/.kube/config
./gen-records.sh
~/.venvs/vks/bin/python sync.py            # diff
~/.venvs/vks/bin/python sync.py --apply    # aplica
```

Credencial do MikroTik: item pessoal do Vaultwarden (lido com a API key do
Secret `vaultwarden-sync-secrets`, contexto `oci-lag0`); requer
`cryptography` (`~/.venvs/vks/bin/python`). Nada é impresso.

## Adicionar um serviço novo

1. Crie o VirtualService no ton-cluster com host `novo.lag0.com.br`
   (`istio-system/lag0-gateway` já tem `*.lag0.com.br` e o cert wildcard).
2. `./gen-records.sh && python sync.py --apply` — o CNAME entra sozinho.
3. Nada a fazer no NetBird: a rota é por IP (`/32`), não por nome.

Publicar o nome na Cloudflare **não** é necessário enquanto o acesso for só
pela malha; se precisar de acesso público, aí é outro caminho (tunnel).

## Verificação

```bash
# da LAN
dig +short fluxer.lag0.com.br              # -> istio-ton... 192.168.88.190
# de um peer fora da LAN (ex. ton-holanda)
netbird networks list                      # istio-vip 192.168.88.190/32  Selected
curl -s -o /dev/null -w '%{http_code} %{remote_ip}\n' https://fluxer.lag0.com.br/
# 200 192.168.88.190
```

Prova de que o acesso é **só** pelo NetBird: com `netbird down` no peer, os
nomes caem na Cloudflare pública (`188.114.9x.x`) e devolvem **403**; com o
túnel de pé voltam a `200` no `.190`.

## Pitfalls

- **Cache duplo.** MikroTik e Technitium cacheiam. Depois de mexer nos
  registros, `sync.py --apply` já faz `POST /rest/ip/dns/cache/flush` no
  roteador; o Technitium expira no TTL do registro público (5 min) — flush
  nele exige sessão de API e reinicia o pod (~2–3 min de DNS fora), então
  prefira esperar.
- **Não usar wildcard `*.lag0.com.br` no MikroTik.** Passaria a capturar
  `harbor`, `nb`, `mail` e o apex, que precisam de resposta pública.
- **Esses registros não estão no fluxo do Flux.** O MikroTik é configuração
  manual; rode `sync.py` depois de qualquer mudança no gateway para não deixar
  serviço novo inacessível de fora de casa.
- **HTTP != DNS.** 503/404 em alguns nomes é serviço sem endpoint (ex.
  `harbor-ton`, `phpldapadmin`, `signoz`) — o nome e a rota estão certos.
