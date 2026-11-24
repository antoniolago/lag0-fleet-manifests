# super-productivity — app web com login OIDC e espaço por usuário

Super Productivity (to-do/time-tracking open source) servido como app web no
`ton-cluster`, com **login único pelo Pocket ID** (`id.lag0.com.br`) e **um espaço
de sincronização isolado por pessoa**, derivado do e-mail que o IdP devolve.

```
internet ──► productivity.lag0.com.br (Cloudflare) ──► túnel ──► istio-gateway
                                                                   │
                       ┌───────────────────────────────────────────┴──────────┐
                       │ /dav/*                                              │ /
                       ▼                                                     ▼
                dav-gateway (nginx)                                 oauth2-proxy:4180
                auth_request ──► oauth2-proxy/oauth2/auth                   │
                X-Auth-Request-Email = identidade                           ▼
                       │                                      super-productivity-web:8080
                       ▼                                             (SPA do app)
                dav (dufs:5000) /data/u/<email>/…
```

## Estado

| Item | Valor |
|---|---|
| URL | https://productivity.lag0.com.br |
| Login | Pocket ID (client OIDC `Super Productivity`) — qualquer conta do IdP entra |
| Namespace | `super-productivity` |
| App | `docker.io/johannesjo/super-productivity:v20.1.0` |
| Sync | WebDAV em `https://productivity.lag0.com.br/dav`, um diretório por e-mail |
| Dados | `pvc/dav-data` → `/data/u/<email>/super-productivity/sync-data.json` |

## A pessoa faz isso uma vez

1. abre https://productivity.lag0.com.br e entra com a conta do Pocket ID;
2. `Configurações → Sincronização → Configurar sincronização`;
3. URL, usuário e pasta já vêm preenchidos (`WEBDAV_*` no Deployment). Falta só
   **digitar qualquer senha** e salvar — o gateway ignora a senha, quem autentica
   é o cookie OIDC; o campo existe porque o app exige.

Depois disso o sync é automático.

## Como funciona o isolamento

`dav-gateway` faz `auth_request` no `oauth2-proxy`, que responde
`X-Auth-Request-Email` **a partir do token do Pocket ID** (nunca de header vindo do
cliente), e o nginx reescreve o caminho para `/u/<email>/…`. Sem sessão, `/dav/…`
responde `401`; ninguém alcança o diretório de outra pessoa.

## Segredo (fora do Git)

`oauth2-proxy-super-productivity` no namespace `super-productivity`, chaves
`client-id`, `client-secret` e `cookie-secret` (32 bytes, `openssl rand -base64 32`).
O par do client vem do Pocket ID; `redirect_uri` registrado:
`https://productivity.lag0.com.br/oauth2/callback`.

## Fechar o acesso a um grupo (opcional)

Por padrão qualquer conta do Pocket ID entra. Para restringir: crie o grupo no
Pocket ID, ligue o client `Super Productivity` a ele (*allowed user groups*) e
acrescente `--allowed-group=<grupo>` nos args do `oauth2-proxy`. Sem a ligação no
IdP o login falha com *You are not allowed to access this service*.

## Limites conhecidos

- Sync WebDAV genérico é marcado como *not recommended* pelo próprio app (o
  provider "oficial" é SuperSync, que **não** tem login OIDC). Aqui ele funciona:
  PUT/GET/PROPFIND e o primeiro upload real foram validados.
- O estado local continua no navegador; em navegador compartilhado duas contas
  usariam o mesmo armazenamento local e sincronizariam para o espaço de quem
  estiver logado. Por device, não há problema.
