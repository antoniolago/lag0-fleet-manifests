# Instruções para criar o item no Vaultwarden
#
# O vaultwarden-kubernetes-secrets já sincroniza automático.
# Basta criar um item na organização "kubernetes-secrets" com:
#
# Nome: gmod-secrets
# Tipo: Secure Note
# Fields:
#   - rcon_password    (oculto)  → senha do RCon
#   - server_password  (texto)   → senha do servidor (vazio = sem senha)
#   - steam_web_api_key (oculto) → chave da Steam Web API
#
# Acesse: https://vw.lag0.com.br → Organization "kubernetes-secrets" → Add Item
# Após criar, o vaultwarden-kubernetes-secrets sincroniza em ~30s.
# 
# O secret será criado em todos os namespaces gmod-* automaticamente
# se tiver a label: oracle.vault.pessoal: "true"
