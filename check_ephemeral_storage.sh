#!/usr/bin/env bash
  
kubectl proxy --append-server-path &
  
set -eo pipefail
  
{
    echo "NODE NAMESPACE POD EPHEMRAL_USED"
    for node in $(kubectl get nodes -o=jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
        curl -fsSL "http://127.0.0.1:8001/api/v1/nodes/$node/proxy/stats/summary" |
            yq '.pods[] | [.podRef.namespace, .podRef.name, .ephemeral-storage.usedBytes] | join(" ")' |
            while read -r namespace name usedBytes; do
                # A pod might have no running containers and consequently no ephemeral-storage usage.
                echo "$node" "$namespace" "$name" "$(numfmt --to iec "${usedBytes:-0}")"
            done
    done | sort -k4,4rh
} | column -t