# Bitwarden Sync Secrets

This Kubernetes deployment automatically syncs secrets from your Vaultwarden/Bitwarden collections to Kubernetes secrets, organized by namespaces using description tags.

## Features

- ✅ **Dual Authentication**: Supports both API key and admin token authentication
- ✅ **API Key Authentication**: Recommended method using Vaultwarden API key
- ✅ **Admin Token Authentication**: Alternative method using admin token
- ✅ **Namespace Organization**: Secrets are organized by namespace tags in descriptions
- ✅ **Automatic Namespace Creation**: Can automatically create namespaces if enabled
- ✅ **Multiple Item Types**: Supports login, secure notes, cards, and identity items
- ✅ **CronJob Scheduling**: Runs automatically on a configurable schedule

## Setup Instructions

### Choose Authentication Method

You can use either **API Key Authentication** (recommended) or **Admin Token Authentication**.

#### Option A: API Key Authentication (Recommended)

1. **Generate API Key in Vaultwarden:**
   - Log into your Vaultwarden web interface
   - Go to **Settings** > **Account** > **Security** > **API Keys**
   - Click **"New API Key"**
   - Give it a name (e.g., "k8s-sync")
   - Copy the **Key ID** and **Secret**

2. **Create the Secret:**
   - Edit `secret-example.yaml` and configure the API key section
   - Encode your credentials:
     ```bash
     # Encode your API Key ID
     echo -n "your-actual-api-key-id" | base64
     
     # Encode your API Key Secret
     echo -n "your-actual-api-key-secret" | base64
     ```

#### Option B: Admin Token Authentication

1. **Get Admin Token from Vaultwarden:**
   - Log into your Vaultwarden web interface
   - Go to **Settings** > **Account** > **Security** > **API Keys**
   - Copy your admin token

2. **Create the Secret:**
   - Edit `secret-example.yaml` and configure the admin token section
   - Encode your admin token:
     ```bash
     echo -n "your-actual-admin-token" | base64
     ```

### 3. Apply the Secret

```bash
kubectl apply -f secret-example.yaml
```

### 4. Configure Bitwarden Structure

1. Create a collection in your Vaultwarden vault (personal or organization):
   - **Collection Name**: `bitwarden-sync-secrets` (or customize via `ROOT_COLLECTION_NAME`)

2. Add secrets to the collection with namespace tags in descriptions:
   - Format: `#namespace:production`, `#namespace:staging`, etc.
   - Example: `"Database credentials #namespace:production"`
   - Example: `"API Key for frontend and backend #namespace:frontend #namespace:backend"`

### 5. Deploy the Sync

```bash
kubectl apply -k .
```

### 6. Enable the CronJob

The CronJob is suspended by default. To enable it:

```bash
kubectl patch cronjob bitwarden-sync -n bitwarden-sync-secrets -p '{"spec":{"suspend":false}}'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BW_URL` | `https://vw.lag0.com.br` | Your Vaultwarden instance URL |
| `BW_ORGANIZATION_ID` | (empty) | Organization ID (leave empty for personal collection) |
| `ROOT_COLLECTION_NAME` | `bitwarden-sync-secrets` | Root collection name |
| `SECRET_NAME_PREFIX` | `bitwarden-secrets` | Secret name prefix |
| `CREATE_NAMESPACES` | `true` | Auto-create namespaces |

### CronJob Schedule

The default schedule runs every minute. To change it, edit the `schedule` field in `cronjob-sync.yaml`:

```yaml
spec:
  schedule: "*/5 * * * *"  # Run every 5 minutes
```

## Monitoring

### Check CronJob Status
```bash
kubectl get cronjobs -n bitwarden-sync-secrets
```

### View Logs
```bash
# Get the latest job
kubectl get jobs -n bitwarden-sync-secrets

# View logs
kubectl logs -n bitwarden-sync-secrets -l job-name=bitwarden-sync-<timestamp>
```

### Check Created Secrets
```bash
# List all namespaces with bitwarden-secrets
kubectl get secrets --all-namespaces | grep bitwarden-secrets
```

## Security

- Supports both API key and admin token authentication
- API key authentication is recommended for better security
- Secrets are stored as Kubernetes secrets
- RBAC controls access to namespaces and secrets
- Optional authentication methods allow flexibility

## Troubleshooting

### Authentication Issues
- Verify your credentials in the secret (API key or admin token)
- Check that the Vaultwarden URL is correct
- Ensure the credentials have proper permissions
- Make sure you're using only one authentication method (not both)

### Collection Not Found
- Verify the collection name matches `ROOT_COLLECTION_NAME`
- Check if using organization vs personal collection
- Ensure the API key has access to the collection

### Namespace Issues
- Check if `CREATE_NAMESPACES` is set to `true`
- Verify the service account has namespace creation permissions
- Check for namespace tags in secret descriptions

## License

MIT License - see the header in `cronjob-sync.yaml` for details. 