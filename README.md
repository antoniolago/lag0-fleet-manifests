# 🚀 My Personal Kubernetes Fleet

Hey there! 👋 Welcome to my personal Kubernetes infrastructure. This is where I manage my two clusters: **"ton"** (my home's cluster composed of 2 mini pcs and a raspberry pi as NAS) and **"oke"** (Oracle Cloud cluster). https://github.com/antoniolago/lag0-fleet-infra and https://github.com/antoniolago/lag0-fleet-infra-ton contains the infrastructure configurations.

## 🏗️ What's Running Here? (or not anymore but cool to have in tree)

- **Vaultwarden** - My password manager (like Bitwarden, but self-hosted)
- **Harbor** - Private container registry for my images and mirror of docker.io
- **Cert-Manager** - Automatic SSL certificates
- **Tailscale** - VPN mesh network
- **CS16 Surf Servers** - Counter-Strike 1.6 surf maps (for the nostalgia)
- **Zomboid Server** - Project Zomboid multiplayer server (heavy!)
- **Jellyfin** - Installed but for now Stremio has been more practical, no self host tho :( 
- **SteamCMD** - Steam game server management
- **Nextcloud** - Used for a while, found it slow and buggy, changed for seafile.
- **Seafile** - The way to store files, fast, simple and reliable.
- **Portainer** - Disabled, k9s >
- **Selenium Grid** - For botting =)
- **Memos** - installed but changed my mind
- **Discord Ticket Bot** - Automated discord support system, not my cup of tea.
- **Movim** - XMPP chat server, dont remember why
- **Mailu** - Email server (because why rely on Gmail?)
- **AdGuard Home** - Found it too buggy, pihole helm chart is more reliable.
- **PostgreSQL** - Various databases for my apps
- **CouchDB** - Document database
- **Alluxio** - Data orchestration (not my area tho)
- **NFS Server** - Network file storage (nfs server to share the same Oracle Block Volume to all oke cluster)
- **Prometheus + Grafana** - Monitoring everything
- **Weave GitOps** - GitOps dashboard
- **Kubero** - Application deployment platform
- **External Secrets** - Secure secret management, syncs data from oracle vault

## 🔧 How I Manage This Mess

I use **GitOps** with Flux to manage everything. The basic flow:
1. I make changes to these YAML files
2. Push to Git
3. Flux automatically applies changes to my clusters
4. Magic happens ✨

### Secret Management
All sensitive stuff (passwords, API keys) lives in **Vaultwarden** and gets pulled in via **vaultwarden-kubernetes-secrets**. No hardcoded secrets here! (except the ones changed after inits)


## 🚨 For the Curious

- **Are all applications working?** - no, a lot of stuff I dont even use anymore so I wouldnt know
- **Probably over-engineering** - But that's half the fun
