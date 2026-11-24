# super-productivity — app web com login OIDC (Pocket ID)

Super Productivity (to-do/time-tracking open source) servido como app web no
`ton-cluster`, com **login único pelo Pocket ID** (`id.lag0.com.br`) na frente de
tudo: quem não autentica no IdP não chega na aplicação.

```
internet ──► productivity.lag0.com.br (Cloudflare, proxy) ──► túnel
                                                                │
                                                    istio-gateway (192.168.88.190)
                                                                │
                                                    oauth2-proxy:4180  ── OIDC ──► id.lag0.com.br
                                                                │
                                                    super-productivity-web:8080 (nginx/SPA)
```

## Estado

| Item | Valor |
|---|---|
| URL | https://productivity.lag0.com.br |
| Login | Pocket ID (client OIDC `Super Productivity`) |
| Namespace | `super-productivity` |
| Imagem | `docker.io/johannesjo/super-productivity:v20.1.0` (build web do próprio autor) |
| Réplicas | 1 web + 1 oauth2-proxy |
| Dados | no navegador de cada pessoa (IndexedDB/localStorage) — o app é local-first |

## O que existe aqui

- `web-deployment.yaml` — o app (nginx com fallback de SPA e `APP_PORT=8080`).
- `oauth2-proxy.yaml` — front-door OIDC. Todos os requests passam por ele; ele
  fala com `https://id.lag0.com.br` e só libera depois do login.
- `services.yaml`, `virtualservices.yaml` — Service/ClusterIP e a rota no
  `istio-system/lag0-gateway` para `productivity.lag0.com.br`.

## Segredo (criado fora do Git)

`oauth2-proxy-super-productivity` no namespace `super-productivity`, com as chaves
`client-id`, `client-secret` e `cookie-secret` (32 bytes, `openssl rand -base64 32`).
O `client-id`/`client-secret` vêm do client OIDC **Super Productivity** no Pocket ID;
o `redirect_uri` registrado é `https://productivity.lag0.com.br/oauth2/callback`.

## Adicionar/remover pessoas

Não há lista local: quem tem conta no Pocket ID entra. Para fechar o acesso a um
grupo, crie o grupo no Pocket ID (`Administration → User Groups`), ligue o client
`Super Productivity` a ele (`allowed user groups`) e acrescente
`--allowed-group=<grupo>` nos args do `oauth2-proxy`.

## Limite conhecido (e por quê)

O Super Productivity web é **client-side**: não tem contas nem banco no servidor.
A autenticação OIDC identifica quem está usando (e bloqueia terceiros), mas os
tarefas ficam no armazenamento do navegador de cada pessoa — não há sincronização
entre dispositivos. O backend de sync oficial (SuperSync) **não fala OIDC**: ele
cria contas próprias com verificação por e-mail/magic link. Por isso ele ficou de
fora deste deploy.

Para sincronizar entre dispositivos há dois caminhos, ambos exigindo credencial
própria (não OIDC): SuperSync (conta própria) ou WebDAV/Nextcloud. Se um dia isso
entrar, é um Deployment a mais neste namespace — o front-door OIDC continua igual.
