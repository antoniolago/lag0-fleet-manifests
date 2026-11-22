#!/usr/bin/env python3
"""Exporta métricas de tráfego da ton-holanda para o node_exporter (textfile collector).

Fontes:
  * `wg show wt0 dump`            -> contadores por peer (persistentes enquanto a interface existe)
  * `netbird status --json`       -> nome/IP/estado de cada peer + contadores do daemon
  * `vnstat --json`               -> acumulados diários/mensais do eth0 (sobrevivem a reboot)

Escreve /var/lib/node_exporter/ton_traffic.prom de forma atômica.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

OUT = Path("/var/lib/node_exporter/ton_traffic.prom")
CONF = Path("/etc/ton-traffic.conf")
WAN = "eth0"
TUN = "wt0"
NB_SUFFIX = ".netbird.lag0.com.br"
HISTORY_DAYS = 14


def run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


def esc(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def peer_meta() -> dict:
    """publicKey/netbirdIp -> metadados do peer, segundo o NetBird."""
    meta: dict[str, dict] = {}
    raw = run(["netbird", "status", "--json"])
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return meta
    for p in (data.get("peers") or {}).get("details") or []:
        ip = p.get("netbirdIp") or ""
        name = (p.get("fqdn") or ip).replace(NB_SUFFIX, "")
        item = {
            "name": name,
            "ip": ip,
            "state": p.get("status") or "unknown",
            "conn": p.get("connectionType") or "-",
            "nb_rx": int(p.get("transferReceived") or 0),
            "nb_tx": int(p.get("transferSent") or 0),
        }
        if p.get("publicKey"):
            meta[p["publicKey"]] = item
        if ip:
            meta.setdefault(ip, item)
    return meta


def wg_peers() -> list[dict]:
    rows = []
    for line in run(["wg", "show", TUN, "dump"]).splitlines():
        f = line.split("\t")
        if len(f) < 8:
            continue  # primeira linha é a própria interface
        allowed = [a for a in f[3].split(",") if a]
        rows.append(
            {
                "key": f[0],
                "endpoint": "" if f[2] == "(none)" else f[2],
                "ip": allowed[0].split("/")[0] if allowed else "",
                "handshake": int(f[4] or 0),
                "rx": int(f[5] or 0),
                "tx": int(f[6] or 0),
            }
        )
    return rows


def vnstat(iface: str = WAN) -> dict:
    out = {"total": (0, 0), "month": (0, 0), "day": (0, 0), "history": [], "month_label": ""}
    try:
        data = json.loads(run(["vnstat", "--json"]) or "{}")
    except json.JSONDecodeError:
        return out
    for entry in data.get("interfaces") or []:
        if entry.get("name") != iface:
            continue
        traffic = entry.get("traffic") or {}

        def pair(item: dict | None) -> tuple[int, int]:
            if not item:
                return (0, 0)
            return (int(item.get("rx") or 0), int(item.get("tx") or 0))

        out["total"] = pair(traffic.get("total"))
        if traffic.get("month"):
            out["month"] = pair(traffic["month"][-1])
            d = traffic["month"][-1].get("date") or {}
            out["month_label"] = f"{d.get('year', 0):04d}-{d.get('month', 0):02d}"
        if traffic.get("day"):
            out["day"] = pair(traffic["day"][-1])
            for item in traffic["day"][-HISTORY_DAYS:]:
                d = item.get("date") or {}
                label = f"{d.get('year', 0):04d}-{d.get('month', 0):02d}-{d.get('day', 0):02d}"
                out["history"].append((label, *pair(item)))
        break
    return out


def quota() -> int:
    if not CONF.exists():
        return 0
    for line in CONF.read_text().splitlines():
        line = line.strip()
        if line.startswith("TON_QUOTA_BYTES="):
            try:
                return int(line.split("=", 1)[1].strip().strip('"'))
            except ValueError:
                return 0
    return 0


def iface_bytes(name: str) -> tuple[int, int]:
    try:
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            if ":" not in line:
                continue
            dev, rest = line.split(":", 1)
            if dev.strip() != name:
                continue
            f = rest.split()
            return int(f[0]), int(f[8])
    except OSError:
        pass
    return (0, 0)


def build() -> str:
    meta = peer_meta()
    lines: list[str] = []
    add = lines.append
    peers = wg_peers()

    def labels_for(peer: dict) -> tuple[str, str]:
        info = meta.get(peer["key"]) or meta.get(peer["ip"]) or {}
        name = info.get("name") or peer["ip"] or "desconhecido"
        return name, f'peer="{esc(name)}",ip="{peer["ip"]}"'

    add("# HELP ton_holanda_peer_info Metadados do peer do NetBird visto pela ton-holanda.")
    add("# TYPE ton_holanda_peer_info gauge")
    for peer in peers:
        info = meta.get(peer["key"]) or meta.get(peer["ip"]) or {}
        add(
            f'ton_holanda_peer_info{{{labels_for(peer)[1]},'
            f'state="{esc(info.get("state") or "unknown")}",'
            f'connection="{esc(info.get("conn") or "-")}"}} 1'
        )

    add("# HELP ton_holanda_peer_rx_bytes Bytes recebidos do peer pelo túnel (upload do peer via exit node).")
    add("# TYPE ton_holanda_peer_rx_bytes counter")
    for peer in peers:
        add(f"ton_holanda_peer_rx_bytes{{{labels_for(peer)[1]}}} {peer['rx']}")

    add("# HELP ton_holanda_peer_tx_bytes Bytes enviados ao peer pelo túnel (download do peer via exit node).")
    add("# TYPE ton_holanda_peer_tx_bytes counter")
    for peer in peers:
        add(f"ton_holanda_peer_tx_bytes{{{labels_for(peer)[1]}}} {peer['tx']}")

    add("# HELP ton_holanda_peer_handshake_age_seconds Idade do último handshake WireGuard do peer.")
    add("# TYPE ton_holanda_peer_handshake_age_seconds gauge")
    now = int(time.time())
    active = 0
    for peer in peers:
        labels = labels_for(peer)[1]
        age = now - peer["handshake"] if peer["handshake"] else 0
        if peer["handshake"] and age < 180:
            active += 1
        add(f"ton_holanda_peer_handshake_age_seconds{{{labels}}} {age}")

    add("# HELP ton_holanda_peers_active Peers com handshake nos últimos 3 minutos.")
    add("# TYPE ton_holanda_peers_active gauge")
    add(f"ton_holanda_peers_active {active}")

    add("# HELP ton_holanda_peer_netbird_rx_bytes Contador rx do daemon NetBird (zera quando a conexão cai).")
    add("# TYPE ton_holanda_peer_netbird_rx_bytes counter")
    seen: set[str] = set()
    for peer in wg_peers():
        info = meta.get(peer["key"]) or meta.get(peer["ip"]) or {}
        name = info.get("name") or peer["ip"] or "desconhecido"
        if name in seen:
            continue
        seen.add(name)
        add(f'ton_holanda_peer_netbird_rx_bytes{{peer="{esc(name)}"}} {info.get("nb_rx", 0)}')
    add("# HELP ton_holanda_peer_netbird_tx_bytes Contador tx do daemon NetBird (zera quando a conexão cai).")
    add("# TYPE ton_holanda_peer_netbird_tx_bytes counter")
    for name in seen:
        nb_tx = 0
        for info in meta.values():
            if (info.get("name") or "") == name:
                nb_tx = info.get("nb_tx", 0)
                break
        add(f'ton_holanda_peer_netbird_tx_bytes{{peer="{esc(name)}"}} {nb_tx}')

    v = vnstat()
    add("# HELP ton_holanda_traffic_total_rx_bytes Acumulado rx do eth0 desde a criação da base vnstat.")
    add("# TYPE ton_holanda_traffic_total_rx_bytes counter")
    add(f"ton_holanda_traffic_total_rx_bytes {v['total'][0]}")
    add("# HELP ton_holanda_traffic_total_tx_bytes Acumulado tx do eth0 desde a criação da base vnstat.")
    add("# TYPE ton_holanda_traffic_total_tx_bytes counter")
    add(f"ton_holanda_traffic_total_tx_bytes {v['total'][1]}")
    add("# HELP ton_holanda_traffic_month_rx_bytes Rx do mês corrente no eth0 (base vnstat).")
    add("# TYPE ton_holanda_traffic_month_rx_bytes gauge")
    add(f"ton_holanda_traffic_month_rx_bytes {v['month'][0]}")
    add("# HELP ton_holanda_traffic_month_tx_bytes Tx do mês corrente no eth0 (base vnstat).")
    add("# TYPE ton_holanda_traffic_month_tx_bytes gauge")
    add(f"ton_holanda_traffic_month_tx_bytes {v['month'][1]}")
    add("# HELP ton_holanda_traffic_day_rx_bytes Rx de hoje no eth0 (base vnstat).")
    add("# TYPE ton_holanda_traffic_day_rx_bytes gauge")
    add(f"ton_holanda_traffic_day_rx_bytes {v['day'][0]}")
    add("# HELP ton_holanda_traffic_day_tx_bytes Tx de hoje no eth0 (base vnstat).")
    add("# TYPE ton_holanda_traffic_day_tx_bytes gauge")
    add(f"ton_holanda_traffic_day_tx_bytes {v['day'][1]}")
    add("# HELP ton_holanda_traffic_history_bytes Total diário do eth0 por dia (base vnstat).")
    add("# TYPE ton_holanda_traffic_history_bytes gauge")
    for label, rx, tx in v["history"]:
        add(f'ton_holanda_traffic_history_bytes{{date="{label}",direction="rx"}} {rx}')
        add(f'ton_holanda_traffic_history_bytes{{date="{label}",direction="tx"}} {tx}')

    rx, tx = iface_bytes(WAN)
    add("# HELP ton_holanda_iface_since_boot_bytes Bytes do eth0 desde o boot (zera em reboot).")
    add("# TYPE ton_holanda_iface_since_boot_bytes counter")
    add(f'ton_holanda_iface_since_boot_bytes{{direction="rx"}} {rx}')
    add(f'ton_holanda_iface_since_boot_bytes{{direction="tx"}} {tx}')

    add("# HELP ton_holanda_quota_bytes Cota mensal de tráfego do plano (0 = não configurada).")
    add("# TYPE ton_holanda_quota_bytes gauge")
    add(f"ton_holanda_quota_bytes {quota()}")
    add("# HELP ton_holanda_month_info Mês corrente segundo o vnstat.")
    add("# TYPE ton_holanda_month_info gauge")
    add(f'ton_holanda_month_info{{month="{v["month_label"] or "desconhecido"}"}} 1')
    add("# HELP ton_holanda_exporter_last_run_seconds Timestamp da última execução do exporter.")
    add("# TYPE ton_holanda_exporter_last_run_seconds gauge")
    add(f"ton_holanda_exporter_last_run_seconds {now}")

    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    fd, tmp = tempfile.mkstemp(dir=str(OUT.parent), prefix=".ton_traffic.", suffix=".prom")
    with os.fdopen(fd, "w") as fh:
        fh.write(payload)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
