# Webmail (Bulwark) — webmail.lag0.com.br

Webmail JMAP nativo para o Stalwart, com login **OIDC via Pocket ID** (PKCE).
Bulwark fala JMAP direto com `mail.lag0.com.br` — nenhum IMAP no meio, e a senha
nunca passa pelo webmail (o browser usa o token do IdP).

```
browser ──https──► webmail.lag0.com.br (Cloudflare tunnel → istio lag0-gateway)
                        │
                        └─► bulwark:3000 (ton-cluster, ns webmail, PVC local-path)
                                │  JMAP (CORS permissivo)
                                └─► https://mail.lag0.com.br
browser ──OIDC──► id.lag0.com.br (Pocket ID, client `webmail`, grupo mail-users)
```

## Pontos que travam o setup

- **CORS no Stalwart**: o browser chama o JMAP direto, então o servidor precisa de
  `x:Http` com `usePermissiveCors: true` (singleton). Sem isso o preflight volta 204 sem
  `access-control-allow-origin` e o app fica em branco. Só vale depois de reiniciar o pod.
- **Issuer privado**: `id.lag0.com.br` resolve para o VIP interno do istio
  (`192.168.88.190`), então `OAUTH_ALLOW_PRIVATE_ENDPOINTS=true` é obrigatório — sem ele o
  Bulwark recusa o discovery por guard de SSRF.
- **RFC 8707**: o Stalwart espera `resource=https://mail.lag0.com.br` no `/authorize`;
  é o `OAUTH_RESOURCE`. Sem ele o authorize falha com `invalid_request`.
- **Client no Pocket ID**: público + PKCE, callback exata
  `https://webmail.lag0.com.br/auth/callback`, `isGroupRestricted: true` +
  `allowed-user-groups: [mail-users]`. O `PUT /api/oidc/clients/{id}` **não grava
  `callbackUrls`** nesta versão — crie o client já com as callbacks no POST e confirme
  pelo `/authorize` (303 para `/interaction` = aceito; `error=You are not allowed to access
  this service` = grupo não ligado).
- **Persistência**: `/app/data` guarda config do admin e sessões; uid **1001** dentro da
  imagem. Em hostPath é preciso um initContainer que faça `chown -R 1001:1001`.

## DNS

`webmail.lag0.com.br` → CNAME `cf.lag0.com.br` (proxied), o mesmo padrão dos outros apps
publicados pelo `lag0-gateway`. O certificado é o wildcard `*.lag0.com.br` já montado no
gateway — não há Certificate novo.

## Admin

`ADMIN_PASSWORD` vem do Secret `bulwark-env` (ns webmail); o admin fica em
`https://webmail.lag0.com.br/admin`. Depois do primeiro boot o hash vai para
`admin.json` e a variável pode ser removida.
