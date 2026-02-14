---
title: "feat(n8n): deploy n8n with community-charts/n8n and Tailscale Funnel for MCP"
labels: ["n8n", "claude-assignable"]
assignees: ["jtcressy"]
---

## Summary

Deploy n8n to the Kubernetes cluster using the **community-charts/n8n** Helm chart (v1.16.28), with PostgreSQL backend (CNPG), Tailscale ingress for the UI, and a separate Tailscale Funnel ingress for the MCP endpoint.

## Helm Chart

- **Repo**: `https://community-charts.github.io/helm-charts`
- **Chart**: `n8n`
- **Version**: `1.16.28`
- **Source**: https://github.com/community-charts/helm-charts/tree/main/charts/n8n
- **Image override**: `n8nio/n8n:2.8.3@sha256:649e3667ecb156674fc97430653e8c42c34fc02c280a634ca3807d09357cf3ea`

## Overlay Path

```
kubernetes/deploy/home/n8n/n8n/clusters/bastion/
├── kustomization.yaml       # helmCharts block + extra resources
├── values.yaml              # community-charts/n8n values
├── externalsecret.yaml      # 1Password → n8n-secret
├── persistence.yaml         # PVC on cephfs + VolSync backup
└── mcp-ingress.yaml         # Second ingress with Tailscale Funnel
```

## Implementation Details

### kustomization.yaml
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - externalsecret.yaml
  - persistence.yaml
  - mcp-ingress.yaml
helmCharts:
  - name: n8n
    repo: https://community-charts.github.io/helm-charts
    version: 1.16.28
    releaseName: n8n
    valuesFile: values.yaml
```

### values.yaml (key sections)
- **Image**: override to `n8nio/n8n:2.8.3` with pinned digest
- **Database**: `DB_TYPE=postgresdb`, `DB_POSTGRESDB_*` env vars from n8n-secret
- **Encryption key**: `N8N_ENCRYPTION_KEY` from n8n-secret via `envFrom`
- **Timezone**: `GENERIC_TIMEZONE=America/Chicago`
- **Diagnostics**: disabled
- **Security context**: `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`
- **Resources**: 10m CPU request, 512Mi memory limit
- **Init container**: `ghcr.io/home-operations/postgres-init:18` with envFrom n8n-secret
- **UI Ingress** (chart-provided):
  ```yaml
  ingress:
    enabled: true
    className: tailscale
    hosts:
      - host: n8n
        paths:
          - path: /
            pathType: Prefix
    tls:
      - hosts:
          - n8n
  ```
- **Persistence**: chart's built-in persistence disabled (we manage PVC separately for VolSync compatibility)
- **envFrom**: reference `n8n-secret` for all sensitive env vars

### mcp-ingress.yaml (raw manifest)
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: n8n-mcp
  annotations:
    tailscale.com/funnel: "true"
spec:
  ingressClassName: tailscale
  tls:
    - hosts:
        - n8n-mcp
  rules:
    - host: n8n-mcp
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: n8n
                port:
                  number: 5678
```

### externalsecret.yaml
- Source: `ClusterSecretStore/onepassword`
- Target: `n8n-secret`
- Extract from 1Password items: `n8n`, `cloudnative-pg`, `sonarr`, `radarr`, `prowlarr`
- Template data: DB credentials, init-postgres vars, encryption key, *arr API keys

### persistence.yaml
- PVC `n8n` on `cephfs`, 5Gi, `ReadWriteOnce`
- Mount at `/home/node/.n8n` (via chart `main.extraVolumes` + `main.extraVolumeMounts`)
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
