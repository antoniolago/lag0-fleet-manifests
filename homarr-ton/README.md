# Homarr — dashboard da casa

`https://homarr.lag0.com.br` — login via Pocket ID (OIDC, auto-login), sem senha local.

## O que estava quebrado

O HelmRelease não tinha **persistência**. O container rodava com filesystem efêmero
(`/appdata` no overlay da imagem), então:

- cada `rollout restart` apagava banco, usuários, boards e o setup;
- o app voltava para o wizard de primeira execução e travava em
  *"An administrator already exists. Sign in to resume setup"*;
- o grupo `lag0` tinha permissão de admin mas estava **vazio** — ninguém conseguia retomar.

Correção (neste diretório): `persistence.homarrDatabase.enabled: true` (2 Gi, `local-path`),
`timeout` da release de 20s → 5m, e `AUTH_OIDC_GROUPS_ATTRIBUTE`/`SCOPE` explícitos.

## Acesso

- **Admin do Homarr**: qualquer membro do grupo `admins` do Pocket ID (hoje só o dono).
  O nome do grupo externo é configurado no wizard e fica gravado no banco.
- **Usuários**: todo mundo que entra por OIDC cai no grupo `everyone`.
- **Break-glass local**: usuário `admin` (provider `credentials`), desativado porque
  `AUTH_PROVIDERS=oidc`. Para usar, suba com `AUTH_PROVIDERS=credentials,oidc`,
  faça login e volte. A senha está em `~/.homarr-breakglass` (chmod 600).

## Boards

| Board | Quem vê | Conteúdo |
|---|---|---|
| `lag0` | grupo `everyone` (view) | Casa, Mídia, Comunicação, Desenvolvimento, Infra |
| `admin` | grupo `admins` (view) | Proxmox, Grafana, Rancher, Nomad, Hermes ×3, RustFS |

## Limite importante

O Homarr só tem **permissão por board**, não por tile. Quem vê o board vê todos os tiles
dele. Por isso os apps que o dono quer só para si (Proxmox, Chatwoot, Soultify, Hermes,
Rancher, Nomad, Grafana, RustFS) ficam no board `admin`, e a autorização de verdade
continua no Pocket ID (o app em si recusa login de quem não está no grupo).

## Tiles removidos

Apps cujo host não resolve ou devolve 404 saíram do board: AdGuard, Upsnap, Vikunja,
Jellyfin, Chatwoot, Soultify. Voltam quando os serviços estiverem de pé.

## Estado atual

- 24 tiles em 6 seções, status (verde/vermelho) por ping HTTP.
- Tema Tokyo Night, pt-BR, Assistant desligado, analytics desligado.
