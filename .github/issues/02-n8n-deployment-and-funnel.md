---
title: "feat(n8n): deploy n8n with app-template and Tailscale Funnel for MCP"
labels: ["n8n", "claude-assignable"]
assignees: ["jtcressy"]
---

## Summary

Deploy n8n to the Kubernetes cluster using the bjw-s app-template Helm chart, with PostgreSQL backend (CNPG), Tailscale ingress for the UI, and Tailscale Funnel for the MCP endpoint.

## Overlay Path

```
kubernetes/deploy/home/n8n/n8n/clusters/bastion/
├── kustomization.yaml
├── values.yaml
├── externalsecret.yaml
└── persistence.yaml
```

## Implementation Details

### kustomization.yaml
- Helm chart: `bjw-s-labs/app-template` v4.5.0
- Release name: `n8n`
- Resources: `persistence.yaml`, `externalsecret.yaml`

### values.yaml
- **Image**: `docker.io/n8nio/n8n:2.8.3@sha256:649e3667ecb156674fc97430653e8c42c34fc02c280a634ca3807d09357cf3ea`
- **Port**: 5678
- **Init container**: `ghcr.io/home-operations/postgres-init:18` for DB provisioning
- **Environment variables**:
  - `N8N_PORT=5678`
  - `N8N_PROTOCOL=https`
  - `GENERIC_TIMEZONE=America/Chicago`
  - `N8N_DIAGNOSTICS_ENABLED=false`
  - `N8N_ENCRYPTION_KEY` from secret
  - `DB_TYPE=postgresdb`
  - `DB_POSTGRESDB_*` from secret
  - `WEBHOOK_URL=https://n8n-mcp.<tailnet>.ts.net` (set after Funnel hostname is known)
- **Security context**: `runAsUser: 1000`, `runAsGroup: 1000`, `readOnlyRootFilesystem: true`
- **Resources**: 10m CPU request, 512Mi memory limit
- **Two ingresses**:
  1. `app` — `className: tailscale`, host `n8n` (UI, Tailscale-only)
  2. `mcp` — `className: tailscale`, host `n8n-mcp`, annotation `tailscale.com/funnel: "true"` (MCP endpoint, public)

### externalsecret.yaml
- Source: `ClusterSecretStore/onepassword`
- Target: `n8n-secret`
- Extract from 1Password items: `n8n`, `cloudnative-pg`, `sonarr`, `radarr`, `prowlarr`
- Template data:
  - `N8N_ENCRYPTION_KEY`, DB credentials, init-postgres vars
  - *arr API keys for use as env vars in n8n (optional — can also configure in n8n credentials UI)

### persistence.yaml
- PVC `n8n` on `cephfs`, 5Gi, `ReadWriteOnce`
- Mount at `/home/node/.n8n`
- VolSync ReplicationSource for backup to R2

## Tailscale Funnel

The MCP ingress uses `tailscale.com/funnel: "true"`. This requires:
- [ ] Tailscale ACL policy allows Funnel for `tag:k8s` or the specific node
- [ ] The Tailscale operator is v1.90+ (currently v1.90.9 — confirmed)

Public URL will be: `https://n8n-mcp.<tailnet-name>.ts.net`

## Dependencies

- Issue #1 (1Password secrets must exist first)

## Acceptance Criteria

- [ ] ArgoCD picks up the overlay and creates the Application
- [ ] n8n pod is running and healthy
- [ ] PostgreSQL database `n8n` is created by init container
- [ ] UI is accessible via `https://n8n.<tailnet>.ts.net`
- [ ] MCP endpoint is accessible via `https://n8n-mcp.<tailnet>.ts.net` (Funnel)
- [ ] `curl https://n8n-mcp.<tailnet>.ts.net/healthz` returns 200 from public internet
