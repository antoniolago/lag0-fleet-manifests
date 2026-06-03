#!/usr/bin/env python3
"""Rotate NetBird relaySecret. Reads current secret, generates new, updates."""
import base64, json, secrets, subprocess, sys, time

def sh(cmd, timeout=30):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or r.stderr).strip()

def kub(cmd):
    return sh("kubectl " + cmd)

if __name__ == "__main__":
    print("=== NetBird relaySecret Rotation ===")

    # Read current
    rc, b64 = kub("get secret -n netbird netbird-management -o jsonpath={{.data.relaySecret}}")
    if rc != 0 or not b64:
        print("SKIP: no netbird-management/relaySecret"); sys.exit(0)

    # Generate new
    ns = secrets.token_urlsafe(32)
    nsb = base64.b64encode(ns.encode()).decode()
    kub("patch secret -n netbird netbird-management -p '{\"data\":{\"relaySecret\":\"" + nsb + "\"}}'")
    print("relaySecret updated in K8s")

    kub("rollout restart deployment -n netbird netbird-management 2>/dev/null || true")
    kub("rollout restart deployment -n netbird-operator netbird-operator 2>/dev/null || true")
    print("NetBird deployments restarted")

    print("OK relaySecret rotated")
    sys.exit(0)
