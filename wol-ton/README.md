# wol-ton — Wake-on-LAN dashboard

Public host: **https://wol.lag0.com.br** (Cloudflare proxied CNAME → `cf.lag0.com.br`, Istio
`lag0-gateway` → Service `upsnap`).

UpSnap ([seriousm4x/UpSnap](https://github.com/seriousm4x/UpSnap)) is a SvelteKit + Go + PocketBase
wake-on-lan dashboard: device cards, one-click magic packet, ping status, cron wake. Login is Pocket ID
over OIDC, so there is no local password to hand out.

## Why the pod runs with hostNetwork

A magic packet is a **layer-2 broadcast**. Sent from the pod network it dies inside the overlay and
never reaches the switch, so the pod is pinned to `ton-cluster-k8s-worker-0` with `hostNetwork: true`
and `dnsPolicy: ClusterFirstWithHostNet`. Worker-0 (192.168.88.204) sits on the bridged `vmbr0`, so the
broadcast leaves through the LAN and any NIC on 192.168.88.0/24 sees it — verified by sending a packet
from the pod and receiving the 102-byte magic payload on another LAN host.

Consequence: the app listens on `192.168.88.204:8090` too. That is the same login page, not a bypass.

## Identity

- Pocket ID client: `upsnap` (`54e90825-2ca0-431a-90d7-56a30b634d69`), confidential, PKCE, callback
  `https://wol.lag0.com.br/api/oauth2-redirect`, restricted to the `hermes-users` user group.
- UpSnap's own login is PocketBase: the provider above is configured in the `users` collection
  (`oauth2.providers[0]`, name `oidc`, display name `Pocket ID`).
- Superuser for the PocketBase console (`/_/`): credentials in Secret **`upsnap-admin`** (created with
  `kubectl`, kept out of git).

## State that lives on the PVC, not in git

The database is UpSnap's own (`upsnap-data` → `/app/pb_data`). These were configured once through the
PocketBase API and are not part of the manifests:

- `settings_public.setup_completed = true` — without it every page redirects to `/welcome/`.
- the OIDC provider on `users` (client id/secret from the Pocket ID client above).
- devices: `lag0-rog` (MAC `b8:8a:60:f3:be:fc`, IP 192.168.88.93, netmask `255.255.255.0`).
- `permissions` record: read/update/delete/power on that device plus `create` for `antonio.lago`.

Losing the PVC means redoing all of it; the steps are below.

## Rebuilding it from scratch

1. Flux applies this directory (`./wol-ton` from `lag0-fleet-infra-ton`). Pod comes up, `/welcome/` says
   the initial superuser is missing.
2. UpSnap's binary always runs `serve`, so PocketBase's CLI commands have to come from a matching
   PocketBase release (`v0.40.4` for UpSnap 5.7.2): `kubectl cp` the binary into the pod and run
   `pocketbase superuser create EMAIL PASS --dir /app/pb_data`.
3. That superuser is invisible to the running app, so set `setup_completed` on the `settings_public`
   record with the superuser token.
4. `PATCH /api/collections/users` with `oauth2.providers[0] = {name: "oidc", clientId, clientSecret,
   authURL: https://id.lag0.com.br/authorize, tokenURL: .../api/oidc/token,
   userInfoURL: .../api/oidc/userinfo, pkce: true, scopes: [openid,email,profile]}`.
5. Create the device, then a `permissions` record for the user that OIDC created on first login —
   without it the dashboard says "Please ask the admin to grant you permissions".

## Pitfalls

- `netmask` must be dotted decimal (`255.255.255.0`). `24` is rejected by the field pattern, and leaving
  the default `255.255.255.255` makes UpSnap send the packet to the device's own IP instead of the
  broadcast address — nothing wakes.
- `devices.id` is a 15-char `[a-z0-9]` primary key; the REST create wants one supplied explicitly.
- Pin the pod against the descheduler (`descheduler.alpha.kubernetes.io/evict: "false"`), and use
  `strategy: Recreate` with the local-path PVC.
- Status stays `offline` while the target blocks ICMP; the ping probe is the only thing it measures.

## Target side (the laptop)

Waking a closed laptop is a firmware/driver question, not this app's:

- **Ethernet** (BIOS/ErP off, NIC "Wake on Magic Packet" + "Shutdown Wake-On-Lan" on, Windows Fast
  Startup off): magic packet works from full shutdown. Add the wired MAC as a second device.
- **WiFi** (Intel AX2xx): only WoWLAN, i.e. the card can wake the machine from sleep/S0ix (and some
  platforms from hybrid shutdown). Enable "Wake on Magic Packet" on the adapter and keep the lid-close
  action as *Sleep*.
