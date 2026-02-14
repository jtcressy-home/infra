---
title: "feat(n8n): connect Claude clients to n8n MCP arr suite tools"
labels: ["n8n", "manual"]
assignees: ["jtcressy"]
---

## Summary

Connect Claude clients (claude.ai web, Claude Mobile, Claude Code, Claude Desktop) to the n8n MCP Server Trigger endpoint exposed via Tailscale Funnel.

## Prerequisites

- n8n deployed with Funnel (issue #2)
- MCP workflow active (issue #3)
- `N8N_MCP_BEARER_TOKEN` value from 1Password

## MCP Endpoint

```
URL: https://n8n-mcp.<tailnet-name>.ts.net/webhook/mcp/<path>
Auth: Bearer <N8N_MCP_BEARER_TOKEN>
Transport: Streamable HTTP
```

## Client Setup

### 1. claude.ai (web) — also syncs to Claude Mobile

1. Go to [claude.ai](https://claude.ai) → Settings → Integrations / Connectors
2. Click "Add custom integration" (or "Add MCP Server")
3. Configure:
   - **Name**: `Arr Suite`
   - **URL**: `https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path>`
   - **Authentication**: Bearer token → paste `N8N_MCP_BEARER_TOKEN`
4. Save and verify tools appear in conversation

> Claude Mobile automatically picks up integrations configured in claude.ai web.

### 2. Claude Code

```bash
claude mcp add --transport http arr-suite \
  https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path> \
  --header "Authorization: Bearer <N8N_MCP_BEARER_TOKEN>"
```

Verify:
```bash
claude mcp list
```

### 3. Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arr-suite": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path>",
        "--header",
        "Authorization: Bearer <N8N_MCP_BEARER_TOKEN>"
      ]
    }
  }
}
```

> Note: Claude Desktop uses stdio, so `mcp-remote` bridges to the HTTP endpoint.
> If Claude Desktop adds native Streamable HTTP support, the config can be simplified.

## Testing

For each client, verify by asking Claude:
- "List my Sonarr series"
- "What movies are in my Radarr queue?"
- "Search for 'The Bear' on Overseerr"

## Acceptance Criteria

- [ ] claude.ai web shows Arr Suite tools available
- [ ] Claude Mobile shows Arr Suite tools available
- [ ] Claude Code can call arr tools
- [ ] Claude Desktop can call arr tools via mcp-remote
