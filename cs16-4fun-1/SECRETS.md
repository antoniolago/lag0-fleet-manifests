# Secrets para cs16-4fun-1

Criar no namespace `cs16-4fun-1`:

## 1. regcred (Harbor auth)

```bash
kubectl create secret docker-registry regcred -n cs16-4fun-1 \
  --docker-server=harbor.lag0.com.br \
  --docker-username='robot$library+actions' \
  --docker-password='<senha-do-robot>'
```

```bash
kubectl patch serviceaccount -n cs16-4fun-1 default \
  -p '{"imagePullSecrets": [{"name": "regcred"}]}'
```

## 2. cs16-4fun-secrets (MySQL)

```bash
kubectl create secret generic cs16-4fun-secrets -n cs16-4fun-1 \
  --from-literal=mysql-password='<sua-senha-aqui>' \
  --from-literal=mysql-root-password='<sua-root-password-aqui>'
```

> O StatefulSet MySQL usa `mysql-password` pro usuário `rank_user` e `mysql-root-password` pro root.
> O servidor CS usa `mysql-password` pra conectar como `rank_user@rank_system`.
