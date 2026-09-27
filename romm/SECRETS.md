# Segredos do RomM — **nada disso vai para o git** (`lag0-fleet-manifests` é público).

O Deployment consome o Secret `romm/romm-secrets` com as chaves abaixo.

## Caminho canônico

1. Criar/atualizar o item no Vaultwarden (organização `kubernetes-secrets`) com **nome `romm-secrets`**
   e os campos exatamente como abaixo (o VKS mapeia nome-do-item → nome-do-Secret e
   nome-do-campo → chave).
2. O VKS sincroniza em ~30s e **sobrescreve** o Secret.

## Campos do item no Vaultwarden

| Campo | Tipo | O que é |
| --- | --- | --- |
| `namespaces` | Text | `romm` |
| `MARIADB_ROOT_PASSWORD` | Hidden | senha do root do MariaDB (gerada, 32 hex) |
| `MARIADB_PASSWORD` | Hidden | senha do usuário `romm-user` — **igual** ao `DB_PASSWD` |
| `ROMM_AUTH_SECRET_KEY` | Hidden | `openssl rand -hex 32` — assina os JWT de sessão do RomM |
| `OIDC_CLIENT_ID` | Text | client `romm` no Pocket ID (`id.lag0.com.br`) |
| `OIDC_CLIENT_SECRET` | Hidden | secret do mesmo client |

## Bootstrap (o que foi feito antes do item existir)

Enquanto o item da organização não existe, o Secret foi criado direto com
`kubectl create secret generic -n romm romm-secrets ...` (as Kustomizations do Flux rodam com
`prune: false`, então o Secret não é removido por não estar no git). **Os valores são exatamente
os mesmos** do item do Vaultwarden — quando o VKS assumir, nada quebra.

Cópia dos valores ficou no cofre **pessoal** do Vaultwarden, no item
`romm-secrets (copiar para a org kubernetes-secrets)`, junto com o spec dos campos.

## OIDC no Pocket ID

- Client: `romm` (confidential)
- Callback URL: `https://romm.lag0.com.br/api/oauth/openid`
- Em *Application Configuration*: **Emails Verified** marcado (o RomM exige email verificado).
- Depois do primeiro login: RomM → **Profile** → colocar o **mesmo email** que o Pocket ID usa
  para você (é o que liga a conta OIDC à conta local do RomM).
- Opcional, para deixar OIDC como único caminho: `DISABLE_USERPASS_LOGIN=true` no deployment.
