# Ollama on Ton Cluster

Ollama is a self-hosted AI model serving platform for running large language models.

## Components

- **Ollama Server**: AI model serving API on port 11434
- **Persistent Storage**: 50Gi PVC for model storage
- **Tailscale Integration**: Exposed via Tailscale VPN
- **GPU Support**: Configured for NVIDIA GPU acceleration

## Access

- **Istio Gateway URL**: `https://ollama.lag0.com.br`
- **Tailscale URL**: `http://ollama-tailscale:11434` (via Tailscale network)
- **Internal Service**: `http://ollama-service.ollama.svc.cluster.local:11434`

## GPU Requirements

- Node selector: `gpu: "true"`
- Requires NVIDIA GPU operator installed
- Requests 1 GPU with 2-8Gi memory allocation

## Usage

### Pull a model
```bash
curl http://ollama-tailscale:11434/api/pull -d '{"name": "llama2"}'
```

### Generate completion
```bash
curl http://ollama-tailscale:11434/api/generate -d '{
  "model": "llama2",
  "prompt": "Why is the sky blue?"
}'
```

## Integration

OpenClaw service is configured to use this Ollama instance for AI-powered features.
