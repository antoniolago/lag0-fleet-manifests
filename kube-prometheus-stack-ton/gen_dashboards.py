#!/usr/bin/env python3
"""Gera os dashboards do Grafana do setup lag0 (4 JSONs provisionados por ConfigMap)."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
OUT.mkdir(parents=True, exist_ok=True)

DS = {"type": "prometheus", "uid": "prometheus"}

COLORS = {
    "blue": "#5794F2",
    "green": "#73BF69",
    "orange": "#FF9830",
    "red": "#F2495C",
    "purple": "#B877D9",
    "yellow": "#FADE2A",
    "teal": "#37B0B0",
}


def tgt(expr, legend, ref="A", instant=False, fmt="time_series"):
    return {
        "datasource": DS,
        "editorMode": "code",
        "expr": expr,
        "legendFormat": legend,
        "refId": ref,
        "instant": instant,
        "range": not instant,
        "format": fmt,
    }


def ts_panel(pid, title, targets, grid, unit="bps", desc="", stack=False, fill=10, legend_calcs=None):
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": grid,
        "targets": targets,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": fill,
                    "gradientMode": "opacity",
                    "showPoints": "never",
                    "spanNulls": False,
                    "stacking": {"mode": "normal" if stack else "none", "group": "A"},
                    "axisPlacement": "auto",
                    "axisSoftMin": 0,
                },
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "bottom",
                "calcs": legend_calcs or ["lastNotNull", "max"],
                "sortBy": "Last *",
                "sortDesc": True,
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def stat_panel(pid, title, expr, grid, unit="none", desc="", color_mode="value", thresholds=None,
               text="", graph="area", instant=True):
    steps = thresholds or [
        {"color": "green", "value": None},
        {"color": "red", "value": 1},
    ]
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": grid,
        "targets": [tgt(expr, title, instant=instant)],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": steps},
                "decimals": 2 if unit == "bps" else 0,
            },
            "overrides": [],
        },
        "options": {
            "colorMode": color_mode,
            "graphMode": graph,
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto" if not text else "value",
        },
    }


def table_panel(pid, title, targets, grid, desc="", overrides=None, transformations=None, unit="none"):
    return {
        "id": pid,
        "type": "table",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": grid,
        "targets": targets,
        "transformations": transformations or [],
        "fieldConfig": {
            "defaults": {"unit": unit, "custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
            "overrides": overrides or [],
        },
        "options": {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {"show": False, "reducer": ["sum"], "countRows": False, "fields": ""},
        },
    }


def bargauge_panel(pid, title, targets, grid, unit="bps", desc=""):
    return {
        "id": pid,
        "type": "bargauge",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": grid,
        "targets": targets,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "color": {"mode": "continuous-GrYlRd"},
                "decimals": 2 if unit == "bps" else 0,
            },
            "overrides": [],
        },
        "options": {
            "orientation": "horizontal",
            "displayMode": "gradient",
            "showUnfilled": True,
            "valueMode": "color",
            "namePlacement": "left",
            "sizing": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
    }


def pie_panel(pid, title, targets, grid, unit="bps", desc=""):
    return {
        "id": pid,
        "type": "piechart",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": grid,
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}}, "overrides": []},
        "options": {
            "pieType": "donut",
            "displayLabels": ["name", "percent"],
            "legend": {"displayMode": "list", "placement": "right", "values": ["value"]},
            "tooltip": {"mode": "single", "sort": "none"},
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
    }


def text_panel(pid, title, content, grid, mode="html"):
    return {
        "id": pid,
        "type": "text",
        "title": title,
        "gridPos": grid,
        "options": {"mode": mode, "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False}, "content": content},
        "fieldConfig": {"defaults": {}, "overrides": []},
    }


def row(pid, title, y):
    return {"id": pid, "type": "row", "title": title, "collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def dashboard(uid, title, panels, description, tags, refresh="30s"):
    return {
        "uid": uid,
        "title": title,
        "description": description,
        "tags": tags,
        "timezone": "browser",
        "editable": True,
        "graphTooltip": 1,
        "refresh": refresh,
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "panels": panels,
        "schemaVersion": 39,
        "version": 1,
    }


# ---------------------------------------------------------------- topologia
TOPO_SVG = """<div style="font-family:Inter,system-ui,sans-serif">
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;font-size:12px;opacity:.8">
  <span><b>Internet</b> → Cloudflare (wildcard *.lag0.com.br) → istio-gateway 192.168.88.190</span>
</div>
<svg viewBox="0 0 1180 470" width="100%" height="430" xmlns="http://www.w3.org/2000/svg">
 <defs>
  <marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#8e9bb3"/></marker>
  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#20293a"/><stop offset="1" stop-color="#161d29"/></linearGradient>
 </defs>
 <style>
  .box{fill:url(#g1);stroke:#3a465c;stroke-width:1.2;rx:10}
  .hdr{fill:#8e9bb3;font:600 11px Inter,sans-serif;letter-spacing:.08em;text-transform:uppercase}
  .t{fill:#e6edf7;font:600 13px Inter,sans-serif}
  .s{fill:#93a1b5;font:11px Inter,sans-serif}
  .ip{fill:#6f7d93;font:10px ui-monospace,monospace}
  .ln{stroke:#46516a;stroke-width:1.4;fill:none;marker-end:url(#ar)}
  .lnd{stroke:#2f3849;stroke-width:1.2;fill:none;stroke-dasharray:5 4}
 </style>

 <rect x="430" y="8" width="320" height="46" rx="10" fill="#1b2432" stroke="#4b5a75"/>
 <text x="590" y="28" text-anchor="middle" class="t">Internet / Cloudflare</text>
 <text x="590" y="44" text-anchor="middle" class="ip">*.lag0.com.br → tunnel → istio-gateway</text>

 <rect x="430" y="86" width="320" height="54" rx="10" fill="#1b2432" stroke="#7b6bd6"/>
 <text x="590" y="106" text-anchor="middle" class="t">istio-gateway · 192.168.88.190</text>
 <text x="590" y="122" text-anchor="middle" class="ip">grafana · netbird · vaultwarden · immich · forgejo · mail</text>

 <rect x="40" y="180" width="500" height="270" rx="12" fill="#131a25" stroke="#2f6f6f"/>
 <text x="58" y="203" class="hdr">ton-cluster · Talos · 192.168.88.200 (VIP)</text>
 <rect x="60" y="216" width="150" height="46" rx="8" class="box"/>
 <text x="72" y="235" class="t">cp-0/1/2</text><text x="72" y="251" class="ip">.201 .202 .203</text>
 <rect x="228" y="216" width="140" height="46" rx="8" class="box"/>
 <text x="240" y="235" class="t">worker-0</text><text x="240" y="251" class="ip">.204 · 8 GB</text>
 <rect x="384" y="216" width="136" height="46" rx="8" class="box"/>
 <text x="396" y="235" class="t">worker-1</text><text x="396" y="251" class="ip">.205 · 8 GB</text>
 <rect x="60" y="276" width="200" height="46" rx="8" class="box"/>
 <text x="72" y="295" class="t">worker-2 (LXC)</text><text x="72" y="311" class="ip">.221 · 26 GB · 4 vCPU</text>
 <rect x="276" y="276" width="244" height="46" rx="8" fill="#1a2433" stroke="#5794F2"/>
 <text x="288" y="295" class="t">prometheus + grafana</text><text x="288" y="311" class="ip">kube-prometheus-stack · Nov 2026</text>
 <rect x="60" y="336" width="460" height="42" rx="8" class="box"/>
 <text x="72" y="362" class="t">apps: immich · vaultwarden · forgejo · matrix · mail · jogos · netbird</text>
 <rect x="60" y="392" width="460" height="42" rx="8" fill="#181f2b" stroke="#3a465c" stroke-dasharray="4 3"/>
 <text x="72" y="410" class="s">MetalLB pool 192.168.88.190-195 · technitium DNS .191 · talos VIP .200</text>
 <text x="72" y="426" class="s">storage: NFS 192.168.88.245 (large-storage) + local-path</text>

 <rect x="640" y="180" width="500" height="140" rx="12" fill="#131a25" stroke="#5a4a86"/>
 <text x="658" y="203" class="hdr">oci-lag0 · OKE · ARM A1.Flex · 137.131.251.88</text>
 <rect x="660" y="216" width="220" height="42" rx="8" class="box"/>
 <text x="672" y="241" class="t">netbird-operator · wg-server</text>
 <rect x="896" y="216" width="226" height="42" rx="8" class="box"/>
 <text x="908" y="241" class="t">istio · harbor · mail (Stalwart)</text>
 <rect x="660" y="268" width="462" height="40" rx="8" class="box"/>
 <text x="672" y="293" class="t">jogos: gmod · cs16 · zomboid (NodePort/UDP via relay)</text>

 <rect x="640" y="340" width="500" height="110" rx="12" fill="#131a25" stroke="#7a6a3a"/>
 <text x="658" y="363" class="hdr">Rede da casa · MikroTik 192.168.88.1</text>
 <text x="658" y="384" class="t">IPFIX → nfcapd :2055 (ton-desktop) → exporter :9101 → Prometheus</text>
 <text x="658" y="403" class="s">ton-desktop .108 · NAS ton00 .245 · Proxmox ton01/02/03 .240/.241/.242</text>
 <text x="658" y="421" class="s">ton-holanda (VPS, borda mail) · peers NetBird 100.82.0.0/16</text>

 <path class="ln" d="M590,54 L590,86"/>
 <path class="ln" d="M590,140 L590,175 L300,175 L300,180"/>
 <path class="ln" d="M590,140 L590,175 L890,175 L890,180"/>
 <path class="lnd" d="M540,230 L640,230"/>
 <text x="556" y="223" class="s">WireGuard 51820 / relay 3478</text>
 <path class="lnd" d="M640,290 L540,300"/>
 <text x="556" y="318" class="s">tráfego de jogo + NetBird</text>
 <path class="lnd" d="M300,360 L300,336"/>
 <path class="lnd" d="M290,392 L290,382"/>
 <text x="110" y="470" class="s">Fonte: kube-state-metrics + node-exporter (painéis ao lado) · IPFIX do MikroTik (dashboard Tráfego)</text>
</svg></div>"""


panels = []
panels.append(text_panel(1, "Mapa do setup", TOPO_SVG, {"h": 14, "w": 24, "x": 0, "y": 0}))
panels.append(row(2, "Saúde agora", 14))
panels.append(stat_panel(3, "Nós Ready", 'sum(kube_node_status_condition{condition="Ready",status="true"})', {"h": 4, "w": 4, "x": 0, "y": 15}, thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 6}], desc="Nós com condição Ready=True. Esperado: 3 control-plane + 3 workers."))
panels.append(stat_panel(4, "Pods Running", "sum(kube_pod_status_phase{phase=\"Running\"})", {"h": 4, "w": 4, "x": 4, "y": 15}))
panels.append(stat_panel(5, "Pods falhando (fora de Job)", 'count(kube_pod_status_phase{phase="Failed"} == 1 unless on(namespace, pod) kube_pod_owner{owner_kind="Job"})', {"h": 4, "w": 4, "x": 8, "y": 15}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 3}], desc="Pods em phase=Failed que não são Jobs concluídos com erro de backup. Aqui sim é problema."))
panels.append(stat_panel(6, "Restarts (1h)", "sum(increase(kube_pod_container_status_restarts_total[1h]))", {"h": 4, "w": 4, "x": 12, "y": 15}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 5}, {"color": "red", "value": 20}]))
panels.append(stat_panel(7, "WAN in (5 min)", "(sum(lag0_flow_total_bytes{direction=\"in\"}) or vector(0)) * 8 / 300", {"h": 4, "w": 4, "x": 16, "y": 15}, unit="bps"))
panels.append(stat_panel(8, "WAN out (5 min)", "(sum(lag0_flow_total_bytes{direction=\"out\"}) or vector(0)) * 8 / 300", {"h": 4, "w": 4, "x": 20, "y": 15}, unit="bps"))
panels.append(row(9, "Recursos por nó", 19))
panels.append(ts_panel(10, "CPU por nó", [tgt('100 - (avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]) * on(instance) group_left(node) label_replace(kube_node_info, "instance", "$1:9100", "internal_ip", "(.*)")) * 100)', "{{node}}")], {"h": 8, "w": 12, "x": 0, "y": 20}, unit="percent"))
panels.append(ts_panel(11, "Memória por nó", [tgt('avg by (node) (100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * on(instance) group_left(node) label_replace(kube_node_info, "instance", "$1:9100", "internal_ip", "(.*)"))', "{{node}}")], {"h": 8, "w": 12, "x": 12, "y": 20}, unit="percent"))
panels.append(row(12, "Rede e exposição", 28))
panels.append(ts_panel(13, "Tráfego por nó (física)", [tgt('sum by (node) (rate(node_network_receive_bytes_total{device=~"en.*|eth.*|br0"}[5m]) * on(instance) group_left(node) label_replace(kube_node_info, "instance", "$1:9100", "internal_ip", "(.*)")) * 8', "rx {{node}}"), tgt('sum by (node) (rate(node_network_transmit_bytes_total{device=~"en.*|eth.*|br0"}[5m]) * on(instance) group_left(node) label_replace(kube_node_info, "instance", "$1:9100", "internal_ip", "(.*)")) * 8', "tx {{node}}", "B")], {"h": 8, "w": 12, "x": 0, "y": 29}, unit="bps"))
panels.append(table_panel(14, "Serviços expostos (LoadBalancer / NodePort)", [
    tgt('kube_service_info{type=~"LoadBalancer|NodePort"}', "{{namespace}}/{{service}}", "A", instant=True),
    tgt('kube_service_spec_type{type=~"LoadBalancer|NodePort"}', "{{namespace}}/{{service}}", "B", instant=True),
    tgt('kube_service_status_load_balancer_ingress', "{{namespace}}/{{service}}", "C", instant=True),
], {"h": 8, "w": 12, "x": 12, "y": 29}, desc="IPs anunciados pelo MetalLB e portas de serviço publicadas.", transformations=[
    {"id": "merge", "options": {}},
    {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "__namespace__": True, "cluster_ip": True, "external_name": True, "job": True, "instance": True, "load_balancer_ip": False, "node_port": False, "port": False, "protocol": False, "service": False, "namespace": False, "type": False, "uid": False, "Value #A": True, "Value #B": True}, "renameByName": {"namespace": "namespace", "service": "serviço", "type": "tipo", "Value #C": "LB IP"}}},
]))

DASH_TOPOLOGY = dashboard(
    "lag0-topology",
    "Lag0 · Topologia & Saúde",
    panels,
    "Mapa vivo do setup: borda Cloudflare/istio, ton-cluster (Talos), OKE, rede da casa com IPFIX e malha NetBird. Dados de kube-state-metrics, node-exporter e do exporter lag0.",
    ["lag0", "topologia", "infra"],
)

# ---------------------------------------------------------------- cluster
panels = []
panels.append(row(1, "Panorama", 0))
panels.append(stat_panel(2, "Nós Ready", 'sum(kube_node_status_condition{condition="Ready",status="true"})', {"h": 4, "w": 4, "x": 0, "y": 1}, thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 6}]))
panels.append(stat_panel(3, "Namespaces", "count(count by (namespace) (kube_pod_info))", {"h": 4, "w": 4, "x": 4, "y": 1}))
panels.append(stat_panel(4, "Deployments indisponíveis", 'count(kube_deployment_status_replicas_unavailable > 0)', {"h": 4, "w": 4, "x": 8, "y": 1}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 3}, {"color": "red", "value": 10}]))
panels.append(stat_panel(5, "Pods Pending", 'sum(kube_pod_status_phase{phase="Pending"})', {"h": 4, "w": 4, "x": 12, "y": 1}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 5}]))
panels.append(stat_panel(6, "Containers não-Ready", 'count(kube_pod_container_status_ready == 0)', {"h": 4, "w": 4, "x": 16, "y": 1}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 3}, {"color": "red", "value": 10}]))
panels.append(stat_panel(7, "PVCs não-Bound", 'count(kube_persistentvolumeclaim_status_phase{phase!="Bound"} == 1)', {"h": 4, "w": 4, "x": 20, "y": 1}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}]))
panels.append(row(8, "Capacidade", 5))
panels.append(ts_panel(9, "CPU: requests vs alocável", [tgt('sum by (node) (kube_node_status_allocatable{resource="cpu"})', "alocável {{node}}"), tgt('sum by (node) (kube_pod_container_resource_requests{resource="cpu"})', "requests {{node}}", "B")], {"h": 8, "w": 12, "x": 0, "y": 6}, unit="short"))
panels.append(ts_panel(10, "Memória: requests vs alocável", [tgt('sum by (node) (kube_node_status_allocatable{resource="memory"})', "alocável {{node}}"), tgt('sum by (node) (kube_pod_container_resource_requests{resource="memory"})', "requests {{node}}", "B")], {"h": 8, "w": 12, "x": 12, "y": 6}, unit="bytes"))
panels.append(row(11, "Carga", 14))
panels.append(ts_panel(12, "Top 10 pods por CPU", [tgt('topk(10, sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!=""}[5m])))', "{{namespace}}/{{pod}}")], {"h": 9, "w": 12, "x": 0, "y": 15}, unit="percentunit", legend_calcs=["lastNotNull", "max"]))
panels.append(ts_panel(13, "Top 10 pods por memória", [tgt('topk(10, sum by (namespace, pod) (container_memory_working_set_bytes{container!=""}))', "{{namespace}}/{{pod}}")], {"h": 9, "w": 12, "x": 12, "y": 15}, unit="bytes"))
panels.append(row(14, "Estado por namespace", 24))
panels.append(table_panel(15, "Pods por namespace e fase", [
    tgt('sum by (namespace, phase) (kube_pod_status_phase) > 0', "{{namespace}} {{phase}}", "A", instant=True),
], {"h": 10, "w": 12, "x": 0, "y": 25}, transformations=[
    {"id": "labelsToFields", "options": {"mode": "columns"}},
    {"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value": "pods", "namespace": "namespace", "phase": "fase"}}},
]))
panels.append(table_panel(16, "Pods reiniciando", [
    tgt('topk(15, sum by (namespace, pod, container) (increase(kube_pod_container_status_restarts_total[6h]))) > 0', "{{namespace}}/{{pod}}:{{container}}", "A", instant=True),
], {"h": 10, "w": 12, "x": 12, "y": 25}, transformations=[
    {"id": "labelsToFields", "options": {"mode": "columns"}},
    {"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value": "restarts", "namespace": "namespace", "pod": "pod", "container": "container"}}},
]))

DASH_CLUSTER = dashboard(
    "lag0-cluster",
    "Lag0 · Cluster & Cargas",
    panels,
    "ton-cluster: capacidade, requests vs alocável, pods que reiniciam e distribuição por namespace.",
    ["lag0", "kubernetes", "capacidade"],
)

# ---------------------------------------------------------------- netbird
panels = []
panels.append(row(1, "Malha", 0))
panels.append(stat_panel(2, "Peers conhecidos", 'sum(lag0_netbird_peers_total{state="total"})', {"h": 4, "w": 4, "x": 0, "y": 1}))
panels.append(stat_panel(3, "Conectados", 'sum(lag0_netbird_peers_total{state="connected"})', {"h": 4, "w": 4, "x": 4, "y": 1}, thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 1}, {"color": "green", "value": 3}]))
panels.append(stat_panel(4, "P2P", 'sum(lag0_netbird_peers_total{state="p2p"})', {"h": 4, "w": 4, "x": 8, "y": 1}, thresholds=[{"color": "orange", "value": None}, {"color": "green", "value": 1}]))
panels.append(stat_panel(5, "Via relay", 'sum(lag0_netbird_peers_total{state="relayed"})', {"h": 4, "w": 4, "x": 12, "y": 1}, thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 2}, {"color": "red", "value": 5}]))
panels.append(stat_panel(6, "Handshake tunel OCI", "max(lag0_wg_handshake_age_seconds)", {"h": 4, "w": 4, "x": 16, "y": 1}, unit="s", thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 120}, {"color": "red", "value": 300}], desc="Idade do último handshake do wg-client com o wg-server do OKE. Acima de ~2 min o túnel está caído."))
panels.append(stat_panel(7, "Tunel OCI: total", "sum(lag0_wg_transfer_bytes)", {"h": 4, "w": 4, "x": 20, "y": 1}, unit="bytes"))
panels.append(row(8, "Peers", 5))
panels.append(table_panel(9, "Estado dos peers", [
    tgt('lag0_netbird_peer_info', "peer", "A", instant=True),
    tgt("rate(lag0_netbird_peer_transfer_bytes{direction=\"rx\"}[5m]) * 8", "rx", "B", instant=True),
    tgt("rate(lag0_netbird_peer_transfer_bytes{direction=\"tx\"}[5m]) * 8", "tx", "C", instant=True),
    tgt("lag0_netbird_peer_latency_seconds", "latência", "D", instant=True),
    tgt("lag0_netbird_peer_handshake_age_seconds", "handshake", "E", instant=True),
], {"h": 11, "w": 15, "x": 0, "y": 6}, desc="Quem está conectado, por qual caminho (P2P ou relay), latência e há quanto tempo houve handshake.", transformations=[
    {"id": "labelsToFields", "options": {"mode": "columns"}},
    {"id": "merge", "options": {}},
    {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "job": True, "instance": True, "layer": True, "fqdn": True, "lag0_netbird_peer_info": True}, "renameByName": {"peer": "peer", "ip": "netbird IP", "status": "status", "connection_type": "caminho", "rx": "rx", "tx": "tx", "latência": "latência", "handshake": "handshake"}}},
], overrides=[
    {"matcher": {"id": "byName", "options": "rx"}, "properties": [{"id": "unit", "value": "bps"}]},
    {"matcher": {"id": "byName", "options": "tx"}, "properties": [{"id": "unit", "value": "bps"}]},
    {"matcher": {"id": "byName", "options": "latência"}, "properties": [{"id": "unit", "value": "s"}]},
    {"matcher": {"id": "byName", "options": "handshake"}, "properties": [{"id": "unit", "value": "s"}]},
    {"matcher": {"id": "byName", "options": "status"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}}, {"id": "mappings", "value": [{"type": "value", "options": {"Connected": {"color": "green", "index": 0}, "Connecting": {"color": "orange", "index": 1}, "Idle": {"color": "text", "index": 2}}}]}]},
    {"matcher": {"id": "byName", "options": "caminho"}, "properties": [{"id": "mappings", "value": [{"type": "value", "options": {"P2P": {"color": "green", "index": 0}, "Relayed": {"color": "orange", "index": 1}}}]}]},
]))
panels.append(ts_panel(10, "Latência por peer", [tgt("lag0_netbird_peer_latency_seconds", "{{peer}}")], {"h": 11, "w": 9, "x": 15, "y": 6}, unit="s", desc="Latência medida pelo próprio NetBird (pings ICE/WireGuard)."))
panels.append(row(11, "Tráfego por peer", 17))
panels.append(ts_panel(12, "Throughput rx por peer", [tgt("rate(lag0_netbird_peer_transfer_bytes{direction=\"rx\"}[5m]) * 8", "{{peer}}")], {"h": 9, "w": 12, "x": 0, "y": 18}, unit="bps"))
panels.append(ts_panel(13, "Throughput tx por peer", [tgt("rate(lag0_netbird_peer_transfer_bytes{direction=\"tx\"}[5m]) * 8", "{{peer}}")], {"h": 9, "w": 12, "x": 12, "y": 18}, unit="bps"))
panels.append(bargauge_panel(14, "Acumulado por peer (rx+tx)", [tgt('sum by (peer) (lag0_netbird_peer_transfer_bytes)', "{{peer}}")], {"h": 9, "w": 12, "x": 0, "y": 27}, unit="bytes"))
panels.append(ts_panel(15, "Tunel WireGuard ton-cluster ↔ OKE", [tgt('rate(lag0_wg_transfer_bytes{direction="rx"}[5m]) * 8', "rx"), tgt('rate(lag0_wg_transfer_bytes{direction="tx"}[5m]) * 8', "tx", "B")], {"h": 9, "w": 12, "x": 12, "y": 27}, unit="bps", desc="Tráfego do wg-client (ton-cluster) até o wg-server no OKE: jogos, relay e management do NetBird."))

DASH_NETBIRD = dashboard(
    "lag0-netbird",
    "NetBird · Peers & Túneis",
    panels,
    "Malha NetBird do lag0: quem está conectado, se o caminho é P2P ou relay, latência, handshakes e throughput por peer. Fonte: netbird status -j (casa-router) e wg show (wg-client).",
    ["lag0", "netbird", "vpn"],
)

# ---------------------------------------------------------------- tráfego
panels = []
panels.append(row(1, "Janela de 5 minutos (IPFIX do MikroTik)", 0))
panels.append(stat_panel(2, "Download", "(sum(lag0_flow_total_bytes{direction=\"in\"}) or vector(0)) * 8 / 300", {"h": 4, "w": 5, "x": 0, "y": 1}, unit="bps", color_mode="background"))
panels.append(stat_panel(3, "Upload", "(sum(lag0_flow_total_bytes{direction=\"out\"}) or vector(0)) * 8 / 300", {"h": 4, "w": 5, "x": 5, "y": 1}, unit="bps", color_mode="background"))
panels.append(stat_panel(4, "Dispositivos ativos", "count(lag0_flow_device_bytes)", {"h": 4, "w": 4, "x": 10, "y": 1}))
panels.append(stat_panel(5, "Conversas na janela", "count(lag0_flow_conversation_bytes)", {"h": 4, "w": 4, "x": 14, "y": 1}))
panels.append(stat_panel(6, "Tráfego sem atribuição", "sum(lag0_flow_unattributed_bytes) * 8 / 300", {"h": 4, "w": 3, "x": 18, "y": 1}, unit="bps", thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1000000}, {"color": "red", "value": 5000000}]))
panels.append(stat_panel(7, "Registros lidos", "sum(lag0_flow_records_window)", {"h": 4, "w": 3, "x": 21, "y": 1}))
panels.append(row(8, "Por dispositivo", 5))
panels.append(bargauge_panel(9, "Top download por dispositivo", [tgt('topk(8, sum by (device) (lag0_flow_device_bytes{direction="in"})) * 8 / 300', "{{device}}")], {"h": 10, "w": 8, "x": 0, "y": 6}))
panels.append(bargauge_panel(10, "Top upload por dispositivo", [tgt('topk(8, sum by (device) (lag0_flow_device_bytes{direction="out"})) * 8 / 300', "{{device}}")], {"h": 10, "w": 8, "x": 8, "y": 6}))
panels.append(pie_panel(11, "Distribuição por protocolo", [tgt(
    'sum by (proto_nome) ('
    'label_replace(label_replace(label_replace(label_replace('
    'sum by (proto) (lag0_flow_service_bytes), '
    '"proto_nome","TCP","proto","6"),"proto_nome","UDP","proto","17"),'
    '"proto_nome","ICMP","proto","1"),"proto_nome","outro","proto",".+"))',
    "{{proto_nome}}")], {"h": 10, "w": 8, "x": 16, "y": 6}, desc="TCP, UDP e ICMP sobre o total da janela."))
panels.append(row(12, "Serviços e conversas", 16))
panels.append(ts_panel(13, "Tráfego por porta de serviço (top 8)", [tgt('topk(8, sum by (port) (lag0_flow_service_bytes{direction="in"})) * 8 / 300', "{{port}} in"), tgt('topk(8, sum by (port) (lag0_flow_service_bytes{direction="out"})) * 8 / 300', "{{port}} out", "B")], {"h": 9, "w": 12, "x": 0, "y": 17}, unit="bps"))
panels.append(ts_panel(14, "Tráfego por dispositivo ao longo do tempo", [tgt('topk(6, sum by (device) (lag0_flow_device_bytes{direction="in"})) * 8 / 300', "{{device}}")], {"h": 9, "w": 12, "x": 12, "y": 17}, unit="bps", desc="Cada série é o total recebido pelo dispositivo na janela de 5 min, convertido para bps. O exporter reescreve a janela a cada minuto."))
panels.append(table_panel(15, "Conversas na janela", [
    tgt('topk(20, lag0_flow_conversation_bytes) * 8 / 300', "{{device}} → {{peer}}:{{port}}", "A", instant=True),
], {"h": 11, "w": 24, "x": 0, "y": 26}, unit="bps", desc="Quem falou com quem e por qual porta, na última janela. IPFIX exporta o retorno pós-NAT; o exporter casa a conversa invertida para atribuir ao host interno.", transformations=[
    {"id": "labelsToFields", "options": {"mode": "columns"}},
    {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "job": True, "instance": True, "layer": True}, "renameByName": {"device": "dispositivo", "peer": "destino", "port": "porta", "proto": "proto", "direction": "direção", "Value": "bps"}}},
    {"id": "sortBy", "options": {"sort": [{"field": "bps", "desc": True}]}},
]))
panels.append(row(16, "Observações", 37))
panels.append(text_panel(17, "Como ler este dashboard", """<b>Fonte:</b> IPFIX exportado pelo MikroTik (192.168.88.1) para o <code>nfcapd</code> na ton-desktop, agregado pelo exporter <code>lag0-metrics</code> em janelas de 5 min.<br>
<ul>
<li><b>Download/Upload</b> = bytes da janela × 8 / 300 s.</li>
<li><b>Por dispositivo</b>: o retorno chega pós-NAT (192.168.0.2); o exporter casa a tupla invertida (proto, IP remoto, porta do serviço, porta local) com a saída do host interno, então o download aparece no dispositivo certo.</li>
<li><b>Sem atribuição</b>: sessões cujo retorno não teve saída correspondente na janela (ex.: fluxo começou antes da janela).</li>
<li><b>Limites honestos</b>: tráfego intra-LAN chaveado não passa pelo roteador; DoH/DoT dentro dos apps não aparece aqui.</li>
</ul>""", {"h": 6, "w": 24, "x": 0, "y": 38}))

DASH_TRAFFIC = dashboard(
    "lag0-traffic",
    "Lag0 · Tráfego da Rede (IPFIX)",
    panels,
    "Quanto cada dispositivo baixa e envia, quais serviços e conversas dominam a janela. Fonte: IPFIX do MikroTik → nfcapd → exporter lag0-metrics.",
    ["lag0", "rede", "ipfix", "trafego"],
    refresh="1m",
)


def write(obj):
    path = OUT / f"{obj['uid']}.json"
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    print(f"{path} panels={len(obj['panels'])}")


for dash in (DASH_TOPOLOGY, DASH_CLUSTER, DASH_NETBIRD, DASH_TRAFFIC):
    write(dash)
