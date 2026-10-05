# AGENTS.md

## Repository scope

`jtcressy-home/infra` is for deployment and GitOps configuration only. Do not add
bespoke application or service implementations here. Custom service code belongs
in a discrete, dedicated project repository; this repository holds its deployment
configuration. If proposed work has unclear scope, ask the owner before adding it.

## Task Runner

This repo uses **Task** (`Taskfile.yml`) as the primary build tool. Always prefer task commands over raw CLI invocations.

- Run `task -l` to discover available tasks before doing things manually
- Use `task apps:overlays:*` for ArgoCD app management — do not manually `git mv` overlay directories

## Critical: ArgoCD Overlay Safety

The ApplicationSet uses `applicationsSync: sync`. **Moving an overlay from `clusters/` to `disabled/` causes ArgoCD to automatically delete the application and all its resources.**

- Always use `task apps:overlays:disable` — never `git mv` to disable an overlay manually
- Use `task apps:overlays:diff` to preview changes before committing
- When introducing a new namespace for an app overlay, update the matching ArgoCD `AppProject` destination before expecting the ApplicationSet app to sync. Prefer `task apps:projects:dest:add` or the existing project YAML pattern, and verify the live `AppProject` has synced before troubleshooting the app rollout.

## Helm Charts

Do **not** use `bjw-s/app-template` for new deployments. Prefer purpose-built community charts or raw Kustomize manifests. Existing apps using app-template are legacy.

## Code Changes → Pull Requests

Always create a PR for any code changes. Post a comment summary (no PR) only for informational/status tasks.

- Draft status is fine while work is in progress, but every PR must be marked ready for review before the task ends. Draft PRs are not reviewed.

## Explore First

Analyze the repo with Explore before making changes. Follow existing patterns for directory structure, YAML style, and naming conventions.

## Obsidian access

- Use the Obsidian connector/MCP tools when the user explicitly asks to ingest from, read, or update Obsidian.
- If Obsidian connector/MCP tools are unavailable for an explicit Obsidian task, stop and ask the user to repair the Obsidian connection or explicitly authorize a non-Obsidian fallback.
- Do not read or write Obsidian notes by filesystem path unless the user explicitly directs that fallback.

## Obsidian write boundary

- Obsidian writes are optional sync actions, not a default lifecycle requirement.
- Ask before substantial note writes.
- When updating Obsidian, follow the vault conventions in `README.md`, relative to the Obsidian vault root.
- Summarize only durable decisions, milestone status, blockers, and next steps back into Obsidian.
