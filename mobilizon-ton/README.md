# Mobilizon on Kubernetes with Istio and CloudNativePG

This directory contains Kubernetes manifests for deploying Mobilizon with PostgreSQL using CloudNativePG and Istio for ingress.

## Prerequisites

- Kubernetes cluster
- Istio installed with ingress gateway
- CloudNativePG operator installed
- cert-manager (for TLS certificates)
- StorageClass configured (default: large-storage)

## Deployment Steps

1. **Create the namespace:**
   ```bash
   kubectl apply -f namespace.yaml
   ```

2. **Deploy storage for uploads:**
   ```bash
   kubectl apply -f uploads-pvc.yaml
   ```

3. **Configure secrets:**
   Edit `secrets.yaml` and update the following values:
   - Generate secret keys with: `gpg --gen-random --armor 1 50`
   - Update POSTGRES_PASSWORD
   - Update MOBILIZON_INSTANCE_HOST to your domain
   - Configure SMTP settings
   
   Edit `postgres-credentials.yaml` and update the database password.
   
   Then apply:
   ```bash
   kubectl apply -f secrets.yaml
   kubectl apply -f postgres-credentials.yaml
   ```

4. **Deploy PostgreSQL with CloudNativePG:**
   ```bash
   kubectl apply -f postgres-cluster.yaml
   ```

5. **Deploy Mobilizon:**
   ```bash
   kubectl apply -f mobilizon.yaml
   kubectl apply -f mobilizon-service.yaml
   ```

6. **Configure Istio Gateway and VirtualService:**
   Update the host in `gateway.yaml` and `virtualservice.yaml` and apply:
   ```bash
   kubectl apply -f gateway.yaml
   kubectl apply -f virtualservice.yaml
   ```

## Creating an Admin User

After deployment, create an admin user:

```bash
kubectl exec -n mobilizon deployment/mobilizon -- mobilizon_ctl users.new "your@email.com" --admin --password "YourPassword"
```

## Updating Mobilizon

To update to the latest version:

```bash
kubectl set image deployment/mobilizon mobilizon=framasoft/mobilizon:latest -n mobilizon
```

## Files Description

- `namespace.yaml` - Kubernetes namespace
- `uploads-pvc.yaml` - PersistentVolumeClaim for Mobilizon uploads
- `secrets.yaml` - Environment variables and secrets
- `postgres-credentials.yaml` - PostgreSQL credentials for CNPG
- `postgres-cluster.yaml` - CloudNativePG Cluster configuration
- `mobilizon.yaml` - Mobilizon application deployment
- `mobilizon-service.yaml` - Mobilizon service
- `gateway.yaml` - Istio Gateway for external access
- `virtualservice.yaml` - Istio VirtualService for routing

## Notes

- CloudNativePG automatically manages PostgreSQL storage and provides read/write services
- The read/write service is named `mobilizon-postgres-rw`
- The read-only service (if needed) is named `mobilizon-postgres-ro`
- Istio Gateway and VirtualService replace traditional Ingress resources
