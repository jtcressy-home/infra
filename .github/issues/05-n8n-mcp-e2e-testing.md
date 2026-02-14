---
title: "test(n8n): validate MCP endpoint end-to-end"
labels: ["n8n", "testing"]
assignees: ["jtcressy"]
---

## Summary

End-to-end validation of the n8n MCP gateway for the *arr suite, covering Tailscale Funnel reachability, MCP protocol compliance, auth enforcement, and tool functionality.

## Prerequisites

- All prior issues (#1-#4) completed

## Test Plan

### 1. Tailscale Funnel Reachability

From a machine **outside** the tailnet (e.g., mobile data, public WiFi):

```bash
# Health check
curl -v https://n8n-mcp.<tailnet>.ts.net/healthz

# Should return 200 OK
```

### 2. MCP Protocol - tools/list

```bash
curl -X POST https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: JSON response listing all *arr tools (sonarr_*, radarr_*, prowlarr_*, overseerr_*).

### 3. Auth Enforcement

```bash
# Without token — should return 401/403
curl -X POST https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Wrong token — should return 401/403
curl -X POST https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### 4. Tool Invocation - Sonarr

```bash
curl -X POST https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sonarr_get_series","arguments":{}},"id":2}'
```

Expected: JSON response with Sonarr series data.

### 5. Tool Invocation - Radarr

```bash
curl -X POST https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"radarr_get_movies","arguments":{}},"id":3}'
```

### 6. Claude Integration Test

From Claude Code:
```
> List all my TV series in Sonarr
> What's in my Radarr download queue?
> Search for "Severance" on Overseerr
```

Each should trigger the corresponding MCP tool call and return real data.

### 7. UI Access (Tailscale-only)

From a machine **on** the tailnet:
```bash
curl -v https://n8n.<tailnet>.ts.net
```
Should return the n8n editor UI (200 OK with HTML).

From **outside** the tailnet, this URL should NOT be reachable (Funnel is only on `n8n-mcp`).

## Acceptance Criteria

- [ ] Funnel reachable from public internet
- [ ] `tools/list` returns all expected tools
- [ ] Unauthenticated requests are rejected
- [ ] Wrong-token requests are rejected
- [ ] At least one tool from each *arr app returns real data
- [ ] Claude Code can invoke tools via MCP
- [ ] n8n UI is accessible only via Tailscale (not public)
