#!/usr/bin/env bash
# Ensure the NetBird mesh objects the Hermes hub (hermes.lag0.com.br) needs.
#
# Mesh-level groups and policies are NetBird objects, not Kubernetes ones: the
# netbird-operator (v0.6.0) can only materialise a policy from an NBResource (the
# ports live on the resource, and that CRD belongs to the netbird "Networks"
# feature), so the plain peer-to-peer policies of this fleet stay in NetBird —
# exactly like the existing `Lag0`, `Subnet Policy` and `SSH Access` objects.
#
# Idempotent, safe to re-run. The API token is never committed: it is read from the
# netbird-operator Secret or passed through $NB_API_KEY.
#
#   ./nb-policies.sh
set -euo pipefail

NBAPI="${NBAPI:-https://netbird.lag0.com.br/api}"
TOKEN="${NB_API_KEY:-$(kubectl --context "${KUBE_CONTEXT:-admin@ton-cluster}" -n netbird-operator \
  get secret netbird-operator-api-key -o jsonpath='{.data.NB_API_KEY}' | base64 -d)}"
[ -n "$TOKEN" ] || { echo "no NetBird API token"; exit 1; }

api() { curl -sS -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" "$@"; }
jqid() { python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))'; }

group_id() {
  api "$NBAPI/groups" | python3 -c '
import json,sys
name=sys.argv[1]
for g in json.load(sys.stdin):
    if g["name"] == name:
        print(g["id"]); break
' "$1"
}

ensure_group() {
  local id; id=$(group_id "$1")
  if [ -z "$id" ]; then
    id=$(api -X POST -d "{\"name\":\"$1\"}" "$NBAPI/groups" | jqid)
    echo "  created group $1 ($id)"
  fi
  echo "$id"
}

# ensure_policy <name> <desc> <srcGroupID> <dstGroupID> <proto> <ports(csv)> <bidir>
ensure_policy() {
  local name="$1" desc="$2" src="$3" dst="$4" proto="$5" ports="$6" bidir="$7"
  local existing body
  existing=$(api "$NBAPI/policies" | python3 -c '
import json,sys
name=sys.argv[1]
for p in json.load(sys.stdin):
    if p["name"] == name:
        print(p["id"]); break
' "$name")
  body=$(python3 - "$name" "$desc" "$src" "$dst" "$proto" "$ports" "$bidir" <<'PY'
import json, sys
name, desc, src, dst, proto, ports, bidir = sys.argv[1:8]
print(json.dumps({
    "name": name,
    "description": desc,
    "enabled": True,
    "rules": [{
        "name": name,
        "description": desc,
        "enabled": True,
        "action": "accept",
        "bidirectional": bidir == "true",
        "protocol": proto,
        "ports": [p.strip() for p in ports.split(",") if p.strip()],
        "sources": [src],
        "destinations": [dst],
    }],
}))
PY
)
  local out
  if [ -n "$existing" ]; then
    out=$(api -X PUT -d "$body" "$NBAPI/policies/$existing")
  else
    out=$(api -X POST -d "$body" "$NBAPI/policies")
  fi
  echo "$out" | python3 -c '
import json,sys
d=json.load(sys.stdin)
if not d.get("id"):
    print("  ERROR:", json.dumps(d)[:300]); sys.exit(1)
r=(d.get("rules") or [{}])[0]
print("  policy", d["name"], "| id=", d["id"],
      "| ports=", r.get("ports"),
      "| bidirectional=", r.get("bidirectional"))
'
}

# ensure_peer_in_group <peerName> <groupID>
ensure_peer_in_group() {
  local peer="$1" gid="$2" peers
  peers=$(api "$NBAPI/groups/$gid" | python3 -c '
import json,sys
gid=sys.argv[1]
g=json.load(sys.stdin)
print(json.dumps([p["id"] for p in (g.get("peers") or [])]))
' "$gid")
  python3 - "$peers" "$peer" "$gid" "$NBAPI" "$TOKEN" <<'PY'
import json, subprocess, sys
peers, peer_name, gid, api, token = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
out = subprocess.run(["curl", "-sS", "-H", f"Authorization: Token {token}", api + "/peers"],
                     capture_output=True, text=True).stdout
match = next((p for p in json.loads(out) if p["name"] == peer_name), None)
if match is None:
    print(f"  peer {peer_name} not registered yet — re-run after it joins the mesh")
    raise SystemExit(0)
if match["id"] in peers:
    print(f"  peer {peer_name} already in the group")
    raise SystemExit(0)
peers.append(match["id"])
body = json.dumps({"name": None, "peers": peers})
# group name is required by the API, read it back from the group
g = json.loads(subprocess.run(["curl", "-sS", "-H", f"Authorization: Token {token}",
                               f"{api}/groups/{gid}"], capture_output=True, text=True).stdout)
body = json.dumps({"name": g["name"], "peers": peers})
subprocess.run(["curl", "-sS", "-X", "PUT", "-H", f"Authorization: Token {token}",
                "-H", "Content-Type: application/json", "-d", body, f"{api}/groups/{gid}"],
               capture_output=True, text=True)
print(f"  added peer {peer_name} to the group")
PY
}

echo "== hermes hub mesh objects =="
HUB_GROUP=$(ensure_group hermes-hub)
LAG0_GROUP=$(ensure_group Lag0)
echo "  hermes-hub=$HUB_GROUP  Lag0=$LAG0_GROUP"

echo "-- policies --"
# Mesh clients (the user's own devices) -> the hub's A2A router (8080) and the
# remote gateway the desktop app dials (9119, `hermes serve`).
ensure_policy "hermes-hub-ingress" \
  "Lag0 -> hub Hermes: A2A router (8080) and desktop remote gateway (9119) of hermes.lag0.com.br" \
  "$LAG0_GROUP" "$HUB_GROUP" tcp 8080,9119 false
# Hub -> the A2A endpoint of every agent on the mesh
ensure_policy "hermes-hub-egress" \
  "hub Hermes -> A2A endpoints of the fleet over netbird" \
  "$HUB_GROUP" "$LAG0_GROUP" tcp 9900 false

echo "-- hub peer membership --"
ensure_peer_in_group hermes-hub "$HUB_GROUP"
