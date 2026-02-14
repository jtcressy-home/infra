# Plan: n8n MCP Gateway for Arr Suite via Tailscale Funnel

## Goal

Deploy n8n in the Kubernetes cluster as an MCP server gateway, exposing tools for the *arr media stack (Sonarr, Radarr, Prowlarr, Overseerr) over Streamable HTTP. Expose via Tailscale Funnel so it's reachable from claude.ai, Claude mobile, Claude Desktop, and Claude Code.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| n8n image tag | `2.8.3@sha256:649e3667ecb156674fc97430653e8c42c34fc02c280a634ca3807d09357cf3ea` | Pinned, released 2026-02-13 |
| n8n database | PostgreSQL via CNPG (`teslamate-db-rw.teslamate.svc.cluster.local`) | Consistent with all other apps |
| n8n UI auth | Tailscale-only (no n8n user/pass) | UI ingress without Funnel, MCP ingress with Funnel + bearer token |
| Workflow storage | Export JSON to git | Reproducibility; store in `resources/mcp-workflow.json` |
| WP2+WP3 | Single PR | Share same `values.yaml` |
| Helm chart | `bjw-s/app-template` v4.5.0 | Matches all other apps in the repo |

## Architecture

```
claude.ai / Claude Mobile / Claude Desktop / Claude Code
    │
    │ Streamable HTTP + Bearer Token
    │ (public internet via Tailscale Funnel)
    ▼
Tailscale Funnel (n8n-mcp.tailnet-name.ts.net:443)
    │
    ▼
┌──────────────────────────────────────────────┐
│  n8n (K8s Deployment, namespace: n8n)        │
│  Image: n8nio/n8n:2.8.3 (pinned digest)     │
│  DB: PostgreSQL on CNPG cluster              │
│  UI Auth: Tailscale-only (no Funnel on UI)   │
│                                              │
│  MCP Server Trigger Workflow:                │
│    ├─ Sonarr tools  → sonarr.media:8989      │
│    ├─ Radarr tools  → radarr.media:7878      │
│    ├─ Prowlarr tools → prowlarr.media:9696   │
│    └─ Overseerr tools → overseerr.media:5055 │
│                                              │
│  API keys from: 1Password → ExternalSecret   │
└──────────────────────────────────────────────┘
```

## n8n Ingress Strategy (Two Ingresses)

1. **UI Ingress** — Tailscale only (no Funnel), hostname `n8n`
   - For accessing n8n editor UI securely via Tailscale
   - No auth required (Tailscale handles access control)
2. **MCP Ingress** — Tailscale Funnel enabled, hostname `n8n-mcp`
   - Public internet access for Claude clients
   - Bearer token auth on the MCP Server Trigger node

## Service Endpoints (cluster-internal)

| Service | Internal DNS | Port |
|---------|-------------|------|
| Sonarr | `sonarr.media.svc.cluster.local` | 8989 |
| Radarr | `radarr.media.svc.cluster.local` | 7878 |
| Prowlarr | `prowlarr.media.svc.cluster.local` | 9696 |
| Overseerr | `overseerr.media.svc.cluster.local` | 5055 |

## Secret Keys Needed (1Password)

Existing keys (already in 1Password):
- `sonarr` → `SONARR_API_KEY`
- `radarr` → `RADARR_API_KEY`
- `prowlarr` → `PROWLARR_API_KEY`

New 1Password item `n8n`:
- `N8N_ENCRYPTION_KEY` — random 32+ char string (n8n internal encryption)
- `N8N_MCP_BEARER_TOKEN` — random token for MCP endpoint auth
- `N8N_POSTGRES_USER` — postgres username for n8n
- `N8N_POSTGRES_PASS` — postgres password for n8n

## PostgreSQL Configuration

```yaml
DB_TYPE: postgresdb
DB_POSTGRESDB_HOST: teslamate-db-rw.teslamate.svc.cluster.local
DB_POSTGRESDB_PORT: "5432"
DB_POSTGRESDB_DATABASE: n8n
DB_POSTGRESDB_USER: "{{ .N8N_POSTGRES_USER }}"
DB_POSTGRESDB_PASSWORD: "{{ .N8N_POSTGRES_PASS }}"
```

Init container: `ghcr.io/home-operations/postgres-init:18` (same as sonarr/radarr/prowlarr)

---

## Work Packages

### WP1: 1Password Secrets Setup (Manual)
Create `n8n` item in 1Password vault with:
- `N8N_ENCRYPTION_KEY`, `N8N_MCP_BEARER_TOKEN`
- `N8N_POSTGRES_USER`, `N8N_POSTGRES_PASS`

### WP2+WP3: n8n Kubernetes Deployment + Tailscale Funnel (Claude Code)
Create overlay at `kubernetes/deploy/home/n8n/n8n/clusters/bastion/`:
- `kustomization.yaml` — app-template v4.5.0 helm chart
- `values.yaml` — n8n 2.8.3 pinned, PostgreSQL env, two ingresses (UI + MCP w/ Funnel)
- `externalsecret.yaml` — 1Password → n8n-secret (DB creds, encryption key, arr API keys)
- `persistence.yaml` — PVC on cephfs + VolSync backup

### WP4: n8n MCP Server Trigger Workflow (Manual, then export JSON to git)
Build workflow in n8n UI with MCP Server Trigger + HTTP Request tool nodes for all *arr APIs.
Export to `resources/mcp-workflow.json`.

### WP5: Claude Connector Setup (Manual per client)
Connect claude.ai, Claude Code, Claude Desktop to the MCP endpoint.

### WP6: Testing & Validation
End-to-end tests of Funnel reachability, MCP tools/list, bearer token enforcement.
