# Tailscale OIDC Integration Guide

This document provides instructions for migrating GitHub Actions workflows from OAuth secret-based authentication to Workload Identity Federation (OIDC) with Tailscale.

## Prerequisites

Before implementing these changes, you need to configure Tailscale for workload identity federation:

1. Go to the [Tailscale Admin Console](https://login.tailscale.com/admin/settings/oauth)
2. Create a new OAuth client for GitHub Actions
3. Configure it with workload identity federation enabled
4. Note the OAuth Client ID (you'll use this as a workflow variable)

Reference: [Tailscale Workload Identity Federation Documentation](https://tailscale.com/kb/1581/workload-identity-federation?q=workload+identity&tab=github+actions)

## Implementation Overview

### Key Changes
- Remove `oauth-secret` parameter (no more secrets!)
- Add `oidc-audience` parameter with your Tailscale OAuth client ID
- Ensure `id-token: write` permission is set on the job
- Add Tailscale step early in the workflow (after checkout, before other operations)

### Workflow Variables

You can define these as repository or organization variables (NOT secrets):

```yaml
vars:
  TAILSCALE_OAUTH_CLIENT_ID: "tsoc-client-xxxxxxxxxxxxx-yyyyyyyyyyyyyyy"
  TAILSCALE_TAGS: "tag:ghactions"
```

## Workflow-Specific Changes

### 1. claude.yml

**Current state:** No Tailscale integration

**Required changes:**
```yaml
jobs:
  claude:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write  # Already present - required for OIDC
      actions: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          fetch-depth: 1

      # ADD THIS STEP HERE (after checkout, before Claude runs)
      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          oidc-audience: ${{ vars.TAILSCALE_OAUTH_CLIENT_ID }}
          tags: ${{ vars.TAILSCALE_TAGS || 'tag:ghactions' }}
          version: 1.60.1  # or latest version

      - name: Run Claude Code
        id: claude
        uses: anthropics/claude-code-action@v1
        # ... rest of configuration
```

**Rationale:** The claude.yml workflow may need Tailscale access if Claude needs to interact with services on your tailnet (e.g., ArgoCD, internal APIs, etc.).

### 2. claude-code-review.yml

**Current state:** No Tailscale integration

**Required changes:**
```yaml
jobs:
  claude-review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write  # Already present - required for OIDC

    steps:
      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          fetch-depth: 1

      # ADD THIS STEP HERE (after checkout, before Claude review runs)
      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          oidc-audience: ${{ vars.TAILSCALE_OAUTH_CLIENT_ID }}
          tags: ${{ vars.TAILSCALE_TAGS || 'tag:ghactions' }}
          version: 1.60.1  # or latest version

      - name: Run Claude Code Review
        id: claude-review
        uses: anthropics/claude-code-action@v1
        # ... rest of configuration
```

**Rationale:** Similar to claude.yml, this enables Claude to access tailnet services during code review.

### 3. argocd-diff.yml

**Current state:** Uses OAuth secrets (old method)

**Before:**
```yaml
- uses: tailscale/github-action@v4
  with:
    oauth-client-id: ${{ secrets.TS_OAUTH_CLIENT_ID }}
    oauth-secret: ${{ secrets.TS_OAUTH_SECRET }}
    tags: tag:ghactions
    version: 1.60.1
```

**After:**
```yaml
jobs:
  argocd-diff:
    name: Generate ArgoCD Diff
    runs-on: ubuntu-latest
    permissions:
      # ADD THIS PERMISSION
      id-token: write
      # ... other permissions as needed
    steps:
      - uses: actions/checkout@v6

      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          oidc-audience: ${{ vars.TAILSCALE_OAUTH_CLIENT_ID }}
          tags: ${{ vars.TAILSCALE_TAGS || 'tag:ghactions' }}
          version: 1.60.1  # or latest version

      # ... rest of workflow
```

**Key changes:**
1. Add `id-token: write` permission to the job
2. Replace `oauth-client-id` and `oauth-secret` with `oidc-audience`
3. Use workflow variable instead of secret for the client ID

## Post-Implementation Steps

After implementing these changes:

1. Set repository/organization variables:
   - `TAILSCALE_OAUTH_CLIENT_ID` - Your Tailscale OAuth client ID
   - `TAILSCALE_TAGS` (optional) - Tags for the Tailscale node (defaults to `tag:ghactions`)

2. Remove old secrets (after verifying OIDC works):
   - `TS_OAUTH_CLIENT_ID`
   - `TS_OAUTH_SECRET`

3. Test each workflow to ensure Tailscale connectivity works

## Security Benefits

Using OIDC instead of OAuth secrets provides:
- No long-lived secrets stored in GitHub
- Automatic token rotation
- Better audit trail (OIDC tokens are tied to specific workflow runs)
- Reduced risk if GitHub Actions logs are compromised

## Troubleshooting

If workflows fail to connect to Tailscale:

1. Verify `id-token: write` permission is set on the job
2. Verify the OAuth client ID is correct in your variables
3. Check Tailscale admin console for authentication attempts
4. Ensure the OAuth client in Tailscale is configured for workload identity federation

## References

- [Tailscale Workload Identity Federation Guide](https://tailscale.com/kb/1581/workload-identity-federation)
- [Tailscale GitHub Action](https://github.com/tailscale/github-action)
- [GitHub OIDC Documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
