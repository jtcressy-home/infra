---
title: "chore(n8n): create 1Password secrets for n8n deployment"
labels: ["n8n", "manual"]
assignees: ["jtcressy"]
---

## Summary

Create a new `n8n` item in the 1Password vault connected to the `onepassword` ClusterSecretStore, containing all secrets needed for the n8n deployment.

## Required Fields

| Field | Description | How to generate |
|-------|-------------|-----------------|
| `N8N_ENCRYPTION_KEY` | n8n internal encryption key for credentials at rest | `openssl rand -hex 32` |
| `N8N_MCP_BEARER_TOKEN` | Bearer token for MCP Server Trigger endpoint auth | `openssl rand -hex 32` |
| `N8N_POSTGRES_USER` | PostgreSQL username for n8n | e.g., `n8n` |
| `N8N_POSTGRES_PASS` | PostgreSQL password for n8n | `openssl rand -base64 32` |

## Context

- The `onepassword` ClusterSecretStore is already configured and used by all *arr apps (sonarr, radarr, prowlarr, overseerr)
- The ExternalSecret in the n8n overlay (issue #2) will extract from this item plus the existing `sonarr`, `radarr`, `prowlarr` items for their API keys
- The `POSTGRES_SUPER_PASS` is already available from the existing `cloudnative-pg` 1Password item

## Acceptance Criteria

- [ ] 1Password item `n8n` exists in the connected vault
- [ ] All 4 fields above are populated with generated values
- [ ] Values are accessible via the `onepassword` ClusterSecretStore (verify with `kubectl get externalsecret` after issue #2 is deployed)

## Blocks

- Issue #2 (n8n deployment) — ExternalSecret won't sync without this item
