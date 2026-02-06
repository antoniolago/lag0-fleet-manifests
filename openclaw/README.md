# OpenClaw on Ton Cluster

OpenClaw is a web-based claw machine game interface integrated with AI capabilities.

## Components

- **OpenClaw Application**: Main web application running on port 8080
- **Persistent Storage**: 1Gi PVC for configuration
- **Tailscale Integration**: Exposed via Tailscale VPN
- **Ollama Integration**: Connected to Ollama service for AI features

## Access

- **Istio Gateway URL**: `https://openclaw.lag0.com.br`
- **Tailscale URL**: `http://openclaw-tailscale` (via Tailscale network)
- **Internal Service**: `http://openclaw-service.openclaw.svc.cluster.local:80`

## Configuration

The application is configured to connect to Ollama at:
- Base URL: `http://ollama-service.ollama.svc.cluster.local:11434`
- Default Model: `llama2`

## Requirements

- Longhorn storage class for persistent volumes
- Tailscale operator for external access
- Ollama service must be running for AI features
