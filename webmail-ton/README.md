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
- **Client no Pocket ID**: público + PKCE, callbacks **com prefixo de locale**
  (`/pt/auth/callback`, `/en/auth/callback`, `/auth/callback`) — o Bulwark monta a URI com
  o idioma da UI, então registrar só a raiz falha com *redirect_uri ... is not registered*.
  `isGroupRestricted: true` + `allowed-user-groups: [mail-users]`, e o client tem de estar
  **linkado à API** `https://mail.lag0.com.br` (`PUT /api/apis/<id>/clients/<client>` com
  `userDelegatedAccess:true`), senão o `/authorize` com `resource=` devolve
  *The 'resource' or 'scope' parameter is invalid*. O `PUT /api/oidc/clients/{id}` **não grava
  `callbackUrls`** nesta versão — crie o client já com as callbacks no POST e confirme
  pelo `/authorize` (303 para `/interaction` = aceito; `error=You are not allowed to access
  this service` = grupo não ligado).
- **Persistência**: `/app/data` guarda config do admin e sessões; uid **1001** dentro da
  imagem. Em hostPath é preciso um initContainer que faça `chown -R 1001:1001`.

## O que o Stalwart precisa aceitar do Bulwark

O token do Bulwark é um JWT do Pocket ID cujo `aud` é
`[https://mail.lag0.com.br, https://id.lag0.com.br]` e cujo `scope` sai apenas
`openid profile email` — o IdP não emite os scopes `urn:ietf:params:oauth:scope:mail`
que o Stalwart usa como base de autorização. Duas mudanças no `Directory/Oidc` são
obrigatórias, e nenhuma das duas aparece como erro no webmail (só `401` no `/jmap`):

- `acceptedAudiences` precisa conter `https://mail.lag0.com.br` (o resource), senão o
  token é recusado por audience.
- `unscopedTokens: interoperable` — sem isso o Stalwart recusa com
  *Token carries none of the urn:ietf:params:oauth:scope… scopes and unscopedTokens is
  set to reject*. `interoperable` libera mail/contacts/calendars/files sem dar
  permissões de administração (use `full` só com audience estrita).
- `x:Account.externalId` = `sub` do usuário no Pocket ID, que é por onde o Stalwart liga
  o token à conta.

## DNS

`webmail.lag0.com.br` → CNAME `cf.lag0.com.br` (proxied), o mesmo padrão dos outros apps
publicados pelo `lag0-gateway`. O certificado é o wildcard `*.lag0.com.br` já montado no
gateway — não há Certificate novo.

Cadeia completa (verificada): `webmail` → `cf` → `6f50e834-…cfargotunnel.com` (túnel
`nb-mgmt`) → ingress `*.lag0.com.br` → `istio-gateway` → VS `webmail/bulwark:3000`.

Como verificar de fora (não adianta `curl` da estação: o DNS local resolve `*.lag0.com.br`
para o VIP `192.168.88.190` e nunca toca a Cloudflare):

```bash
kubectl run probe-$RANDOM -n default --rm -i --restart=Never --image=curlimages/curl:8.10.1 \
  --command -- curl -sSI https://webmail.lag0.com.br | head -3      # espera HTTP/2 200 + x-powered-by: bulwarkmail.org
```

⚠️ **403 "Sorry, you have been blocked" em `curl` não é o webmail quebrado.** A Cloudflare
bloqueia requisições automatizadas vindas de IP de datacenter/egress do `ton-holanda`
(88.216.187.80) — o bloqueio vale para a zona inteira (`lag0.com.br`, `cf`, `backup`…), não só
para este host. Um navegador real do mesmo IP passa (o app abre em `/en/login` e o botão
`Entrar com SSO` leva a `id.lag0.com.br/interaction`). Teste de fumaça por HTTP só é válido
de um IP residencial/cluster (ton-cluster ou oci-lag0).


## Admin

`ADMIN_PASSWORD` vem do Secret `bulwark-env` (ns webmail); o admin fica em
`https://webmail.lag0.com.br/admin`. Depois do primeiro boot o hash vai para
`admin.json` e a variável pode ser removida.
