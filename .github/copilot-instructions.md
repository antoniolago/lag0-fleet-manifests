% Copilot / AI Agent Instructions for lag0-fleet-manifests

Purpose
- Quick, actionable guidance so an AI coding agent can be immediately productive in this repository.

Big picture
- This repo is a GitOps-style collection of Kubernetes manifests and Helm values for many services (per-service folders). Examples: [ingress-nginx](ingress-nginx), [cert-manager](cert-manager), [vaultwarden-ton](vaultwarden-ton).
- Each service directory commonly contains: `kustomization.yaml`, `helm.yaml`, and `namespace.yaml`. Secrets are frequently kept in sibling directories with `-secrets` suffix (e.g. `bitwarden-operator-secrets`).
- Environment/cluster targets are encoded in directory names via suffixes: `-ton`, `-oke`, `-pi` (many services provide per-environment variants).

How the repo is used (discoverable patterns)
- This is a Flux CD environment: changes to manifests are automatically reconciled by Flux controllers in the cluster.
- Primary tools: `kustomize` for manifest composition and `helm` for chart templating (Flux handles the deployment).
- Many directories are structured as independent deployable units; treat each top-level folder as a namespace-scoped component unless its `kustomization.yaml` indicates otherwise.

Conventions and patterns to follow
- Do not attempt to invent global build tooling: prefer making minimal, local changes (edit kustomization, helm values, or manifests in a single component first).
- Secrets are externalized: changes to `*-secrets` directories should be treated cautiously — they may be encrypted or managed by an external secrets controller.
- Use directory suffixes to scope changes: e.g. modify `vaultwarden-ton` for the 'ton' cluster, not `vaultwarden` generically.
- Namespace whiteboxing: `namespace.yaml` files are present to declare namespaces—use them when creating resources programmatically.

Integration points and notable services
- Ingress: `ingress-nginx` and `oci-native-ingress-controller` are present — changes to ingress objects may have cluster-wide effects.
- DNS/certificates: `external-dns`, `cert-manager`, and `technitium-dns-ton` appear in the repo — coordinate name and ACME-related changes accordingly.
- Networking/load-balancing: `metal-lb`, `tailscale-*`, and `submariner-*` components indicate cross-node and cross-cluster networking (be conservative with IP and external address changes).

Developer workflows (practical commands)
- Preview changes locally: `kustomize build path/to/component` or `helm template myrel chart -f path/to/component/helm.yaml`.
- Validate manifests: `kubectl apply -f - --dry-run=client` (using built manifests).
- Monitor Flux reconciliation: Check Flux status in the cluster after commits (Flux automatically applies changes).

Examples to reference when coding
- Per-service kustomize + helm pattern: [vaultwarden-ton/postgres/restore-s3.yaml](vaultwarden-ton/postgres/restore-s3.yaml) and sibling `kustomization.yaml` files.
- Secrets folders: `bitwarden-operator-secrets/` and `vaultwarden-kubernetes-secrets-ton/` show how credentials and kubernetes secrets are grouped.

Agent behavior rules (project-specific)
- Do not commit plaintext secrets. If a change requires secret data, raise an instruction or modify templated values only.
- Keep diffs small and per-component; produce PRs that target a single top-level folder when possible.
- When editing Helm values (`helm.yaml`), preserve the existing key structure; prefer minimal edits rather than wholesale replacements.

When you need clarification
- Ask for the target cluster (ton/oke/pi) before making environment-scoped changes.
- If a change touches ingress/DNS/cert-manager, flag it as potentially disruptive and require human review.

If merging into an existing `.github/copilot-instructions.md`
- Preserve any custom operational notes already present; add or update only repository-specific sections above.

Feedback
- After applying a first draft PR, ask maintainers for examples of the Flux CD pipeline and whether HelmReleases or an external tool renders `helm.yaml` files.
