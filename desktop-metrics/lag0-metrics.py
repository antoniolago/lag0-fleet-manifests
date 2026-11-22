#!/usr/bin/env python3
"""lag0-metrics — Prometheus exporter para o setup lag0.

Duas fontes, um endpoint /metrics:

1. IPFIX do MikroTik, lido dos arquivos do nfcapd (~/flows). Agrega a ultima
   janela de 5 min por origem, por destino:porta e por conversa.
2. NetBird: `netbird status -j` dentro do pod casa-router (peers, tipo de
   conexao, handshake, latencia, bytes) e `wg show` dentro do wg-client
   (tunel com o OKE).

Metricas de janela sao gauges (byte por janela); bps = valor * 8 / janela.
"""
from __future__ import annotations

import csv
import ipaddress
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FLOWS = Path(os.environ.get("FLOWS_DIR", Path.home() / "flows"))
WINDOW = int(os.environ.get("FLOW_WINDOW", "300"))
PORT = int(os.environ.get("EXPORTER_PORT", "9101"))
KUBECTL = os.environ.get("KUBECTL", shutil.which("kubectl") or "/usr/bin/kubectl")
CONTEXT = os.environ.get("KUBE_CONTEXT", "admin@ton-cluster")
NFDUMP = os.environ.get("NFDUMP", shutil.which("nfdump") or "/usr/bin/nfdump")
TOP_N = 250

_lock = threading.Lock()
_cache = {"flow": (0.0, ""), "netbird": (0.0, ""), "error": ""}


def esc(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def is_internal(ip: str) -> bool:
    return ip.startswith("192.168.88.")


def is_lan(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(
        addr in net
        for net in (
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("100.64.0.0/10"),
        )
    )


def load_names() -> dict[str, str]:
    names: dict[str, str] = {}
    static = FLOWS / "hosts-static.json"
    if static.exists():
        try:
            names.update(json.loads(static.read_text()))
        except json.JSONDecodeError:
            pass
    leases = FLOWS / "leases.json"
    if leases.exists():
        try:
            for lease in json.loads(leases.read_text()):
                if lease.get("ip") and lease.get("host"):
                    names[lease["ip"]] = lease["host"]
        except json.JSONDecodeError:
            pass
    return names


def flow_metrics() -> str:
    now = time.time()
    start = now - WINDOW
    fmt = "%Y/%m/%d.%H:%M:%S"
    window = (
        datetime.fromtimestamp(start).strftime(fmt)
        + "-"
        + datetime.now().strftime(fmt)
    )
    try:
        res = subprocess.run(
            [NFDUMP, "-R", str(FLOWS), "-t", window, "-o", "csv", "-q"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.SubprocessError as exc:
        return f'lag0_exporter_flow_error{{reason="{esc(type(exc).__name__)}"}} 1\n'
    if res.returncode != 0:
        return 'lag0_exporter_flow_error{reason="nfdump"} 1\n'

    names = load_names()
    rows: list[tuple[str, str, str, str, str, int]] = []
    for row in csv.reader(res.stdout.splitlines()[1:]):
        if len(row) < 9:
            continue
        proto, sa, sp, da, dp = row[2], row[3], row[4], row[5], row[6]
        try:
            byt = int(row[8])
        except ValueError:
            continue
        if dp == "2055" or sp == "2055":
            continue
        rows.append((proto, sa, sp, da, dp, byt))

    # O RouterOS exporta a saida com o IP da LAN e o retorno ja pos-NAT
    # (192.168.0.2). O mapa abaixo casa o retorno com o host interno pela
    # tupla invertida (proto, ip remoto, porta do servico, porta local).
    reverse: dict[tuple[str, str, str, str], str] = {}
    for proto, sa, sp, da, dp, _ in rows:
        if is_internal(sa) and not is_internal(da):
            reverse[(proto, da, dp, sp)] = sa

    device: dict[str, int] = {}
    service: dict[str, int] = {}
    remote: dict[str, int] = {}
    pair: dict[str, int] = {}
    total_in = total_out = unattributed = records = 0

    for proto, sa, sp, da, dp, byt in rows:
        records += 1
        if is_internal(sa):
            direction, dev, peer, port = "out", sa, da, dp
        elif is_internal(da):
            direction, dev, peer, port = "in", da, sa, sp
        else:
            dev = reverse.get((proto, sa, sp, dp), "")
            if not dev:
                unattributed += byt
                continue
            direction, peer, port = "in", sa, sp
        if direction == "out":
            total_out += byt
        else:
            total_in += byt
        dev_name = names.get(dev, dev)
        peer_name = names.get(peer, peer)
        device[f"{dev}|{dev_name}|{direction}"] = device.get(f"{dev}|{dev_name}|{direction}", 0) + byt
        service[f"{port}|{proto}|{direction}"] = service.get(f"{port}|{proto}|{direction}", 0) + byt
        rkey = f"{peer}|{peer_name}|{port}|{proto}|{direction}"
        remote[rkey] = remote.get(rkey, 0) + byt
        ckey = f"{dev_name}|{peer_name}|{port}|{proto}|{direction}"
        pair[ckey] = pair.get(ckey, 0) + byt

    out: list[str] = []
    out.append("# HELP lag0_flow_window_seconds Tamanho da janela agregada")
    out.append("# TYPE lag0_flow_window_seconds gauge")
    out.append(f"lag0_flow_window_seconds {WINDOW}")
    out.append("# HELP lag0_flow_records_window Registros de flow na janela")
    out.append("# TYPE lag0_flow_records_window gauge")
    out.append(f"lag0_flow_records_window {records}")
    out.append("# HELP lag0_flow_total_bytes Bytes atribuidos na janela por direcao")
    out.append("# TYPE lag0_flow_total_bytes gauge")
    out.append(f'lag0_flow_total_bytes{{direction="in"}} {total_in}')
    out.append(f'lag0_flow_total_bytes{{direction="out"}} {total_out}')
    out.append("# HELP lag0_flow_unattributed_bytes Bytes sem host interno identificado")
    out.append("# TYPE lag0_flow_unattributed_bytes gauge")
    out.append(f"lag0_flow_unattributed_bytes {unattributed}")

    def emit(family: str, help_text: str, labels: list[str], items: dict[str, int]) -> None:
        out.append(f"# HELP {family} {help_text}")
        out.append(f"# TYPE {family} gauge")
        ordered = sorted(items.items(), key=lambda kv: kv[1], reverse=True)
        for key, value in ordered[:TOP_N]:
            parts = key.split("|")
            if len(parts) != len(labels):
                continue
            lbl = ",".join(f'{name}="{esc(val)}"' for name, val in zip(labels, parts))
            out.append(f"{family}{{{lbl}}} {value}")
        rest = sum(value for _, value in ordered[TOP_N:])
        if rest:
            lbl = ",".join(f'{name}="other"' for name in labels)
            out.append(f"{family}{{{lbl}}} {rest}")

    emit(
        "lag0_flow_device_bytes",
        "Bytes por dispositivo da LAN na janela",
        ["ip", "device", "direction"],
        device,
    )
    emit(
        "lag0_flow_service_bytes",
        "Bytes por porta de servico na janela",
        ["port", "proto", "direction"],
        service,
    )
    emit(
        "lag0_flow_remote_bytes",
        "Bytes por destino remoto/porta na janela",
        ["remote", "remote_name", "port", "proto", "direction"],
        remote,
    )
    emit(
        "lag0_flow_conversation_bytes",
        "Bytes por conversa dispositivo->remoto na janela",
        ["device", "peer", "port", "proto", "direction"],
        pair,
    )
    return "\n".join(out) + "\n"


def kubectl_exec(pod: str, command: list[str], container: str | None = None, timeout: int = 25) -> str:
    args = [KUBECTL, "--context", CONTEXT, "-n", "netbird", "exec", pod]
    if container:
        args += ["-c", container]
    args += ["--"] + command
    res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200] or "kubectl exec failed")
    return res.stdout


def size_to_bytes(text: str) -> int:
    text = text.strip()
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4,
             "kB": 1000, "MB": 1000**2, "GB": 1000**3}
    for unit in sorted(units, key=len, reverse=True):
        if text.endswith(unit):
            try:
                return int(float(text[: -len(unit)].strip()) * units[unit])
            except ValueError:
                return 0
    return 0


def netbird_metrics() -> str:
    out: list[str] = []
    errors: list[str] = []

    out.append("# HELP lag0_netbird_peer_connected Peer conectado (1) ou nao (0)")
    out.append("# TYPE lag0_netbird_peer_connected gauge")
    out.append("# HELP lag0_netbird_peer_relayed Peer usando relay (1) ou P2P (0)")
    out.append("# TYPE lag0_netbird_peer_relayed gauge")
    out.append("# HELP lag0_netbird_peer_transfer_bytes Bytes acumulados por peer")
    out.append("# TYPE lag0_netbird_peer_transfer_bytes counter")
    out.append("# HELP lag0_netbird_peer_latency_seconds Latencia medida pelo NetBird")
    out.append("# TYPE lag0_netbird_peer_latency_seconds gauge")
    out.append("# HELP lag0_netbird_peer_handshake_age_seconds Idade do ultimo handshake")
    out.append("# TYPE lag0_netbird_peer_handshake_age_seconds gauge")
    out.append("# HELP lag0_netbird_peer_info Metadados do peer")
    out.append("# TYPE lag0_netbird_peer_info gauge")
    out.append("# HELP lag0_netbird_peers_total Peers por estado")
    out.append("# TYPE lag0_netbird_peers_total gauge")

    try:
        status = json.loads(kubectl_exec("deploy/casa-router", ["netbird", "status", "-j"]))
        peers = status.get("peers") or {}
        out.append(f'lag0_netbird_peers_total{{state="total"}} {int(peers.get("total") or 0)}')
        details = peers.get("details") or []
        connected = sum(1 for p in details if (p.get("status") or "").lower() == "connected")
        relayed = sum(1 for p in details if (p.get("connectionType") or "") == "Relayed")
        p2p = sum(1 for p in details if (p.get("connectionType") or "") == "P2P")
        out.append(f'lag0_netbird_peers_total{{state="connected"}} {connected}')
        out.append(f'lag0_netbird_peers_total{{state="p2p"}} {p2p}')
        out.append(f'lag0_netbird_peers_total{{state="relayed"}} {relayed}')
        now = datetime.now(timezone.utc)
        for peer in details:
            fqdn = peer.get("fqdn") or peer.get("netbirdIp") or "unknown"
            name = fqdn.split(".")[0]
            st = peer.get("status") or "unknown"
            ctype = peer.get("connectionType") or "-"
            ip = peer.get("netbirdIp") or ""
            out.append(
                f'lag0_netbird_peer_info{{peer="{esc(name)}",fqdn="{esc(fqdn)}",ip="{esc(ip)}",'
                f'status="{esc(st)}",connection_type="{esc(ctype)}"}} 1'
            )
            out.append(
                f'lag0_netbird_peer_connected{{peer="{esc(name)}"}} '
                f'{1 if st.lower() == "connected" else 0}'
            )
            out.append(
                f'lag0_netbird_peer_relayed{{peer="{esc(name)}"}} '
                f'{1 if ctype == "Relayed" else 0}'
            )
            out.append(
                f'lag0_netbird_peer_transfer_bytes{{peer="{esc(name)}",direction="rx"}} '
                f'{int(peer.get("transferReceived") or 0)}'
            )
            out.append(
                f'lag0_netbird_peer_transfer_bytes{{peer="{esc(name)}",direction="tx"}} '
                f'{int(peer.get("transferSent") or 0)}'
            )
            latency = peer.get("latency") or 0
            if latency:
                out.append(
                    f'lag0_netbird_peer_latency_seconds{{peer="{esc(name)}"}} {latency / 1e9:.6f}'
                )
            hs = peer.get("lastWireguardHandshake") or ""
            if hs.startswith("20") and not hs.startswith("0001"):
                ts = hs.replace("Z", "+00:00")
                try:
                    hs_dt = datetime.fromisoformat(ts)
                    out.append(
                        f'lag0_netbird_peer_handshake_age_seconds{{peer="{esc(name)}"}} '
                        f'{max((now - hs_dt).total_seconds(), 0):.0f}'
                    )
                except ValueError:
                    pass
    except (RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        errors.append(f'lag0_exporter_netbird_error{{source="casa-router",reason="{esc(type(exc).__name__)}"}} 1')

    out.append("# HELP lag0_wg_transfer_bytes Bytes do tunel WireGuard (wg-client/OCI)")
    out.append("# TYPE lag0_wg_transfer_bytes counter")
    out.append("# HELP lag0_wg_handshake_age_seconds Idade do handshake do tunel WireGuard")
    out.append("# TYPE lag0_wg_handshake_age_seconds gauge")
    try:
        text = kubectl_exec("deploy/wg-client", ["wg", "show"], container="wireguard")
        peer = "oke"
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("peer:"):
                peer = line.split(":", 1)[1].strip()[:16]
            elif line.startswith("transfer:"):
                body = line.split(":", 1)[1]
                rx, tx = body.split(",")
                rx_b = size_to_bytes(rx.replace("received", "").strip())
                tx_b = size_to_bytes(tx.replace("sent", "").strip())
                out.append(
                    f'lag0_wg_transfer_bytes{{peer="{esc(peer)}",direction="rx"}} {rx_b}'
                )
                out.append(
                    f'lag0_wg_transfer_bytes{{peer="{esc(peer)}",direction="tx"}} {tx_b}'
                )
            elif line.startswith("latest handshake:"):
                body = line.split(":", 1)[1].strip()
                seconds = 0
                if "never" in body:
                    seconds = 99999
                else:
                    for amount, unit in re.findall(r"(\d+)\s+(second|minute|hour|day)", body):
                        mult = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit]
                        seconds += int(amount) * mult
                out.append(
                    f'lag0_wg_handshake_age_seconds{{peer="{esc(peer)}"}} {seconds}'
                )
    except (RuntimeError, subprocess.SubprocessError) as exc:
        errors.append(f'lag0_exporter_netbird_error{{source="wg-client",reason="{esc(type(exc).__name__)}"}} 1')

    out.extend(errors)
    return "\n".join(out) + "\n"



def collect() -> str:
    with _lock:
        now = time.time()
        parts: list[str] = []
        flow_ts, flow_text = _cache["flow"]
        if now - flow_ts > 55 or not flow_text:
            flow_text = flow_metrics()
            _cache["flow"] = (now, flow_text)
        parts.append(flow_text)
        nb_ts, nb_text = _cache["netbird"]
        if now - nb_ts > 25 or not nb_text:
            nb_text = netbird_metrics()
            _cache["netbird"] = (now, nb_text)
        parts.append(nb_text)
        return "".join(parts)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/healthz"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.path.startswith("/metrics"):
            self.send_error(404)
            return
        try:
            body = collect().encode()
            code = 200
        except Exception as exc:  # noqa: BLE001
            body = f'lag0_exporter_error{{reason="{esc(type(exc).__name__)}"}} 1\n'.encode()
            code = 500
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # noqa: D102
        pass


if __name__ == "__main__":
    print(f"lag0-metrics ouvindo em :{PORT} (flows={FLOWS}, janela={WINDOW}s)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
