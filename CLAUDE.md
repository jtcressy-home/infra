# CLAUDE.md

## Task Runner

This repo uses **Task** (`Taskfile.yml`) as the primary build tool. Always prefer task commands over raw CLI invocations.

- Run `task -l` to discover available tasks before doing things manually
- Use `task apps:overlays:*` for ArgoCD app management — do not manually `git mv` overlay directories

## Critical: ArgoCD Overlay Safety

The ApplicationSet uses `applicationsSync: sync`. **Moving an overlay from `clusters/` to `disabled/` causes ArgoCD to automatically delete the application and all its resources.**

- Always use `task apps:overlays:disable` — never `git mv` to disable an overlay manually
- Use `task apps:overlays:diff` to preview changes before committing

## Helm Charts

Do **not** use `bjw-s/app-template` for new deployments. Prefer purpose-built community charts or raw Kustomize manifests. Existing apps using app-template are legacy.

## Code Changes → Pull Requests

Always create a PR for any code changes. Post a comment summary (no PR) only for informational/status tasks.

## Explore First

Analyze the repo with Explore before making changes. Follow existing patterns for directory structure, YAML style, and naming conventions.
