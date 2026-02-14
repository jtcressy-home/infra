# Plan: n8n MCP Gateway for Arr Suite via Tailscale Funnel

## Goal

Deploy n8n in the Kubernetes cluster as an MCP server gateway, exposing tools for the *arr media stack (Sonarr, Radarr, Prowlarr, Overseerr) over Streamable HTTP. Expose via Tailscale Funnel so it's reachable from claude.ai, Claude mobile, Claude Desktop, and Claude Code.

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

## Reference: Existing Infrastructure Patterns

| Pattern | How it works in this repo |
|---------|--------------------------|
| Helm via Kustomize | `helmCharts:` block in `kustomization.yaml` with `valuesFile:` |
| App Template | `bjw-s/app-template` chart v4.5.0 |
| Tailscale Ingress | `className: tailscale` on Ingress, automatic TLS |
| Tailscale Funnel | annotation `tailscale.com/funnel: "true"` on Ingress (see searxng, currently commented out) |
| Secrets | `ClusterSecretStore` named `onepassword`, ExternalSecret → target Secret |
| Overlay path | `kubernetes/deploy/{project}/{namespace}/{app}/clusters/bastion/` |
| ArgoCD pickup | Automatic via ApplicationSet matching `kubernetes/deploy/*/*/*/clusters/*` |

## Service Endpoints (cluster-internal)

| Service | Internal DNS | Port |
|---------|-------------|------|
| Sonarr | `sonarr.media.svc.cluster.local` | 8989 |
| Radarr | `radarr.media.svc.cluster.local` | 7878 |
| Prowlarr | `prowlarr.media.svc.cluster.local` | 9696 |
| Overseerr | `overseerr.media.svc.cluster.local` | 5055 |

## Secret Keys Needed (1Password)

Existing keys (already in 1Password, used by the *arr apps themselves):
- `sonarr` → `SONARR_API_KEY`
- `radarr` → `RADARR_API_KEY`
- `prowlarr` → `PROWLARR_API_KEY`

New keys to create in 1Password:
- `n8n` → `N8N_ENCRYPTION_KEY` (n8n's internal encryption key for credentials)
- `n8n` → `N8N_MCP_BEARER_TOKEN` (bearer token for MCP endpoint auth)

---

## Work Packages

### WP1: 1Password Secrets Setup
**Scope:** Create the `n8n` item in 1Password with required secrets.
**Manual step** (cannot be done via GitOps).

Tasks:
1. Create a new 1Password item named `n8n` in the vault connected to the `onepassword` ClusterSecretStore
2. Add field `N8N_ENCRYPTION_KEY` — generate a random 32+ char string
3. Add field `N8N_MCP_BEARER_TOKEN` — generate a random token for MCP auth
4. Add references to existing *arr API keys (or n8n will fetch them from its own credentials store — see WP4 for alternative)

**Dependencies:** None
**Parallelizable:** Yes (independent of all other WPs)

---

### WP2: n8n Kubernetes Deployment
**Scope:** Create the ArgoCD overlay for n8n following existing patterns.
**Output:** Files in `kubernetes/deploy/home/n8n/n8n/clusters/bastion/`

Tasks:
1. Create directory `kubernetes/deploy/home/n8n/n8n/clusters/bastion/`
2. Create `kustomization.yaml` — Helm chart deployment using either:
   - **Option A:** Official n8n Helm chart (`8gears/n8n` or `n8n-io/n8n`)
   - **Option B:** `bjw-s/app-template` chart (matches existing patterns)
   - Recommendation: **Option B** for consistency with the rest of the media stack
3. Create `values.yaml` — app-template values:
   - Image: `docker.io/n8nio/n8n:latest` (or pinned tag)
   - Port: 5678 (n8n default)
   - Env: `N8N_PORT=5678`, `N8N_PROTOCOL=https`, `WEBHOOK_URL`, `N8N_ENCRYPTION_KEY` from secret, `GENERIC_TIMEZONE=America/Chicago`
   - Security context: non-root (n8n runs as UID 1000)
   - Resource limits: 256Mi-512Mi memory, 10m-100m CPU
4. Create `externalsecret.yaml`:
   - Source: `ClusterSecretStore/onepassword`
   - Extract from 1Password item `n8n`
   - Also extract *arr API keys from `sonarr`, `radarr`, `prowlarr` items
   - Target: `n8n-secret`
5. Create `persistence.yaml`:
   - PVC for n8n data (`/home/node/.n8n`): 5Gi on `cephfs`
   - Optional: VolSync backup (can add later)

**Dependencies:** WP1 (secrets must exist)
**Parallelizable:** File creation can happen in parallel with WP1; just won't sync until secrets exist

---

### WP3: Tailscale Funnel Ingress
**Scope:** Create an Ingress with Tailscale Funnel annotation for public exposure.
**Output:** Ingress resource in the n8n overlay OR in values.yaml

Tasks:
1. Add ingress to `values.yaml` (if using app-template):
   ```yaml
   ingress:
     app:
       enabled: true
       className: tailscale
       annotations:
         tailscale.com/funnel: "true"
       hosts:
         - host: n8n-mcp
           paths:
             - path: /
               pathType: Prefix
               service:
                 identifier: app
                 port: http
       tls:
         - hosts:
             - n8n-mcp
   ```
2. Verify Tailscale ACL policy allows Funnel for this node (may need Tailscale admin console change)
3. The public URL will be: `https://n8n-mcp.<tailnet-name>.ts.net`

**Dependencies:** WP2 (deployment must exist)
**Parallelizable:** Can be included in WP2's values.yaml (same file), but Tailscale ACL check is independent

---

### WP4: n8n MCP Server Trigger Workflow
**Scope:** Build the n8n workflow that exposes *arr tools via MCP Server Trigger.
**Manual step** (done in n8n UI after deployment, or exported as JSON and stored in repo).

Tasks:
1. Access n8n UI (via Tailscale or port-forward)
2. Create a new workflow: "Arr Suite MCP Tools"
3. Add **MCP Server Trigger** node:
   - Auth: Bearer token (from `N8N_MCP_BEARER_TOKEN` secret, configured as n8n credential)
   - Path: `/mcp` (default)
4. Add tool nodes connected to MCP Server Trigger:

   **a. Sonarr Tools (HTTP Request nodes):**
   - Search Series: `GET http://sonarr.media:8989/api/v3/series` with API key header
   - Add Series: `POST http://sonarr.media:8989/api/v3/series`
   - Get Queue: `GET http://sonarr.media:8989/api/v3/queue`
   - Get Calendar: `GET http://sonarr.media:8989/api/v3/calendar`
   - Search for Episodes: `POST http://sonarr.media:8989/api/v3/command` (body: `{name: "SeriesSearch"}`)

   **b. Radarr Tools (HTTP Request nodes):**
   - Search Movies: `GET http://radarr.media:7878/api/v3/movie`
   - Add Movie: `POST http://radarr.media:7878/api/v3/movie`
   - Get Queue: `GET http://radarr.media:7878/api/v3/queue`
   - Get Calendar: `GET http://radarr.media:7878/api/v3/calendar`
   - Search for Movie: `POST http://radarr.media:7878/api/v3/command` (body: `{name: "MoviesSearch"}`)

   **c. Prowlarr Tools (HTTP Request nodes):**
   - Search Indexers: `GET http://prowlarr.media:9696/api/v1/search`
   - Get Indexers: `GET http://prowlarr.media:9696/api/v1/indexer`

   **d. Overseerr Tools (HTTP Request nodes):**
   - Search Media: `GET http://overseerr.media:5055/api/v1/search`
   - Request Media: `POST http://overseerr.media:5055/api/v1/request`
   - Get Requests: `GET http://overseerr.media:5055/api/v1/request`
   - Get Trending: `GET http://overseerr.media:5055/api/v1/discover/trending`

5. Configure each HTTP Request node with the API key from n8n credentials
6. Activate the workflow
7. Export workflow JSON and store in repo at `kubernetes/deploy/home/n8n/n8n/clusters/bastion/resources/mcp-workflow.json` for reproducibility

**Dependencies:** WP2 + WP3 (n8n must be running and accessible)
**Parallelizable:** No, requires running n8n instance

---

### WP5: Claude Connector Setup
**Scope:** Connect Claude clients to the n8n MCP endpoint.
**Manual step** per client.

Tasks:
1. **claude.ai (web):**
   - Settings → Connectors → "Add custom connector"
   - Name: `Arr Suite`
   - URL: `https://n8n-mcp.<tailnet-name>.ts.net/webhook/mcp`
   - Auth: Bearer token (the `N8N_MCP_BEARER_TOKEN` value)

2. **Claude Code:**
   ```bash
   claude mcp add --transport http arr-suite \
     https://n8n-mcp.<tailnet-name>.ts.net/webhook/mcp \
     --header "Authorization: Bearer <N8N_MCP_BEARER_TOKEN>"
   ```

3. **Claude Desktop:**
   ```json
   {
     "mcpServers": {
       "arr-suite": {
         "command": "npx",
         "args": [
           "mcp-remote",
           "https://n8n-mcp.<tailnet-name>.ts.net/webhook/mcp",
           "--header",
           "Authorization: Bearer <N8N_MCP_BEARER_TOKEN>"
         ]
       }
     }
   }
   ```

4. **Claude Mobile:** Will automatically pick up connectors added via claude.ai web.

**Dependencies:** WP3 (Funnel must be live) + WP4 (workflow must be active)
**Parallelizable:** All client setups are independent of each other

---

### WP6: Testing & Validation
**Scope:** Verify end-to-end functionality.

Tasks:
1. Test Tailscale Funnel reachability from public internet:
   ```bash
   curl https://n8n-mcp.<tailnet-name>.ts.net/healthz
   ```
2. Test MCP endpoint directly:
   ```bash
   curl -X POST https://n8n-mcp.<tailnet-name>.ts.net/webhook/mcp \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
   ```
3. Test from Claude Code: ask Claude to "list my Sonarr series"
4. Test from claude.ai: same query via web
5. Verify bearer token rejection when omitted

**Dependencies:** WP5
**Parallelizable:** Tests are sequential

---

## Execution Order & Parallelism

```
WP1 (1Password secrets)  ──────────────┐
                                        ├──→ WP2 (K8s deployment)
WP3 (Tailscale ACL check) ────────────┘        │
                                                ├──→ WP4 (n8n workflow)
                                                │         │
                                                │         ├──→ WP5 (Claude connectors)
                                                │         │         │
                                                │         │         ├──→ WP6 (Testing)

Parallel batch 1: WP1 + WP3 (Tailscale ACL check only)
Parallel batch 2: WP2 + WP3 (ingress in values.yaml)
Sequential:       WP4 → WP5 → WP6
```

## GitHub Issues Breakdown (if dispatching separately)

| Issue # | Title | WPs | Assignable to Claude Code? |
|---------|-------|-----|---------------------------|
| 1 | `chore(n8n): create 1Password secrets for n8n deployment` | WP1 | No (manual) |
| 2 | `feat(n8n): deploy n8n with app-template helm chart` | WP2 | Yes |
| 3 | `feat(n8n): enable Tailscale Funnel ingress for MCP endpoint` | WP3 | Yes (file changes), partially manual (ACL) |
| 4 | `feat(n8n): build MCP Server Trigger workflow for arr suite` | WP4 | No (n8n UI, manual) |
| 5 | `docs(n8n): Claude connector setup instructions` | WP5 | Partially (can write docs) |
| 6 | `test(n8n): validate MCP endpoint e2e` | WP6 | Yes (curl tests) |

## Open Questions / Decisions

1. **n8n image tag:** Pin to a specific version or use `latest`? Recommend pinning (e.g., `1.121.1` or newer for instance-level MCP).
2. **n8n database:** SQLite (default, simpler) or PostgreSQL (your CNPG cluster)? SQLite is fine for a single-instance n8n.
3. **n8n auth:** n8n's own UI auth (email/password) vs. disabling it and relying on Tailscale-only access for the UI? The MCP endpoint uses separate bearer token auth regardless.
4. **Workflow storage:** Export workflow JSON to git for reproducibility, or treat n8n as stateful and back up via VolSync only?
5. **Should WP2+WP3 be a single PR?** They share the same `values.yaml` file. Recommend: yes, single PR.
