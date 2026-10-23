# playit.gg — saída UDP para o PZ atrás de CGNAT

O servidor está atrás de CGNAT da Claro: sem IPv4 público e sem IPv6 na LAN, **nada** de fora
alcança 16261/16262. O PZ é IPv4-only, então não existe caminho direto — a única saída sem túnel
OCI é um relay UDP externo. `playit.gg` é o padrão da comunidade para PZ (tier grátis cobre PZ).

## Por que não Steam Relay

O relay do Steam depende da identidade Steam do servidor (`SteamAPI_Init` → “Server Steam ID”).
Neste container ela não completa (`Waiting for response from Steam servers`, `[S_API FAIL]
SteamNetworkingUtils004 before SteamAPI_Init succeeded`, nenhum “Server Steam ID” no log) e, mesmo
completando, a listagem pública exige que o cliente consiga consultar o servidor — impossível
atrás de CGNAT.

## Como ativar (3 passos)

1. Conta grátis em <https://playit.gg> → Setup Wizard → Docker → copiar o **SECRET_KEY**.
2. Criar o Secret no cluster:
   ```bash
   kubectl --context admin@ton-cluster -n zomboid-server-1 create secret generic playit-secret \
     --from-literal=secret-key='<SECRET_KEY>'
   ```
3. Ligar este kustomize no pai (`../kustomization.yaml`, adicionar `- playit`) e criar o túnel no
   dashboard do playit: **UDP**, local `zomboid-server-1.zomboid-server-1.svc.cluster.local`,
   porta **16261**, **Port Count 2** (cobre 16261 e 16262 — não criar dois túneis sobrepostos).

O dashboard devolve um endereço tipo `alguma-coisa.playit.gg:12345`. É esse que os jogadores põem
em Add Server (sem marcar Steam Relay).

## Verificação

```bash
kubectl --context admin@ton-cluster -n zomboid-server-1 logs deploy/zomboid-playit
```

Esperado: `agent connected` e a lista de túneis atribuídos pelo dashboard.
