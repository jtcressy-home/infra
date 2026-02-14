---
title: "feat(n8n): build MCP Server Trigger workflow for arr suite"
labels: ["n8n", "manual"]
assignees: ["jtcressy"]
---

## Summary

Create an n8n workflow using the MCP Server Trigger node that exposes tools for Sonarr, Radarr, Prowlarr, and Overseerr. Export the workflow JSON to git for reproducibility.

## Prerequisites

- n8n is deployed and accessible (issue #2)
- 1Password secrets are configured (issue #1)

## Workflow: "Arr Suite MCP Tools"

### MCP Server Trigger Node
- **Auth**: Bearer token (configure as n8n Header Auth credential using `N8N_MCP_BEARER_TOKEN` value)
- **Path**: `/mcp` (the production URL will be `https://n8n-mcp.<tailnet>.ts.net/webhook/mcp/<path>`)
- **Transport**: Streamable HTTP (supported by n8n 2.x)

### Tool Nodes

Each tool is an HTTP Request node connected to the MCP Server Trigger. All use API key auth via header `X-Api-Key`.

#### Sonarr Tools (base: `http://sonarr.media.svc.cluster.local:8989`)

| Tool Name | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| sonarr_get_series | GET | `/api/v3/series` | List all series in Sonarr |
| sonarr_search_series | GET | `/api/v3/series/lookup?term={query}` | Search for a series by name |
| sonarr_add_series | POST | `/api/v3/series` | Add a new series to Sonarr |
| sonarr_get_queue | GET | `/api/v3/queue` | Get current download queue |
| sonarr_get_calendar | GET | `/api/v3/calendar?start={start}&end={end}` | Get upcoming episodes |
| sonarr_search_command | POST | `/api/v3/command` | Trigger a series search (`{"name":"SeriesSearch","seriesId":N}`) |

#### Radarr Tools (base: `http://radarr.media.svc.cluster.local:7878`)

| Tool Name | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| radarr_get_movies | GET | `/api/v3/movie` | List all movies in Radarr |
| radarr_search_movies | GET | `/api/v3/movie/lookup?term={query}` | Search for a movie by name |
| radarr_add_movie | POST | `/api/v3/movie` | Add a new movie to Radarr |
| radarr_get_queue | GET | `/api/v3/queue` | Get current download queue |
| radarr_get_calendar | GET | `/api/v3/calendar?start={start}&end={end}` | Get upcoming releases |
| radarr_search_command | POST | `/api/v3/command` | Trigger a movie search (`{"name":"MoviesSearch","movieIds":[N]}`) |

#### Prowlarr Tools (base: `http://prowlarr.media.svc.cluster.local:9696`)

| Tool Name | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| prowlarr_search | GET | `/api/v1/search?query={query}&type=search` | Search across all indexers |
| prowlarr_get_indexers | GET | `/api/v1/indexer` | List configured indexers |
| prowlarr_get_indexer_stats | GET | `/api/v1/indexerstats` | Get indexer performance stats |

#### Overseerr/Jellyseerr Tools (base: `http://overseerr.media.svc.cluster.local:5055`)

| Tool Name | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| overseerr_search | GET | `/api/v1/search?query={query}` | Search for movies/TV shows |
| overseerr_request_media | POST | `/api/v1/request` | Submit a media request |
| overseerr_get_requests | GET | `/api/v1/request?take=20&sort=added` | List recent media requests |
| overseerr_get_trending | GET | `/api/v1/discover/trending` | Get trending media |
| overseerr_get_request_status | GET | `/api/v1/request/{id}` | Check status of a specific request |

### n8n Credentials to Configure

1. **Sonarr API**: Header Auth — header `X-Api-Key`, value from 1Password `sonarr` → `SONARR_API_KEY`
2. **Radarr API**: Header Auth — header `X-Api-Key`, value from 1Password `radarr` → `RADARR_API_KEY`
3. **Prowlarr API**: Header Auth — header `X-Api-Key`, value from 1Password `prowlarr` → `PROWLARR_API_KEY`
4. **Overseerr API**: Header Auth — header `X-Api-Key`, value from 1Password `overseerr` (if applicable, or use the main API key)
5. **MCP Bearer Auth**: Header Auth — header `Authorization`, value `Bearer <N8N_MCP_BEARER_TOKEN>`

## Export to Git

After building and testing the workflow:

1. Export workflow JSON from n8n (Settings > Export)
2. Save to: `kubernetes/deploy/home/n8n/n8n/clusters/bastion/resources/mcp-workflow.json`
3. Commit and push

This serves as documentation and allows rebuilding the workflow if the n8n instance is recreated.

## Acceptance Criteria

- [ ] Workflow is active in n8n
- [ ] MCP Server Trigger responds to `tools/list` request
- [ ] All tool nodes are connected and functional
- [ ] Bearer token auth is enforced (unauthenticated requests rejected)
- [ ] Workflow JSON is exported and committed to git
