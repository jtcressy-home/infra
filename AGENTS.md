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

## GSD Project Loop

This repo may use official upstream GSD for scoped infra-repo planning and execution.

### Roles

- GSD is the local planning/execution loop for one active project at a time.
- `.planning/` is private operational state for the current worktree.
- Obsidian is the durable curated project record.
- Codex is the bounded execution harness for code, GitOps, and infra edits.

### Active Project Rule

- Each worktree has one atomic `.planning/` folder.
- Treat the current worktree as owning at most one active GSD project.
- Do not mix unrelated projects in the same `.planning/` state.
- If `.planning/` already exists, infer the active project from `.planning/PROJECT.md`, `.planning/ROADMAP.md`, and `.planning/STATE.md`.
- If `.planning/` does not exist, ask the user which Obsidian project folder should be used as the durable record before starting GSD planning.
- Use vault-root-relative Obsidian paths only, such as `openclaw/index.md` or `some-project/index.md`.
- Do not use absolute filesystem paths for Obsidian notes in instructions, plans, or summaries.

### Project Switching

- Before switching projects in the same worktree, sync the current `.planning/` state back to the appropriate Obsidian project notes.
- After sync, ask the user whether to keep, remove, or leave the old `.planning/` state in place before starting another project.
- Prefer a separate git worktree for each active GSD project when practical.
- A worktree may serve as the durable local legacy for that project's gitignored `.planning/` state while it exists.
- Before deleting, closing, or abandoning a worktree, sync any durable GSD decisions, milestone status, blockers, and next steps back to Obsidian.

### Obsidian Access

- Use the Obsidian connector/MCP tools for Obsidian reads and writes.
- Before project planning, read the selected project's Obsidian index note and its linked current working set.
- If Obsidian connector/MCP tools are unavailable, STOP and ask the user to repair the Obsidian connection before continuing project planning.
- Do not read or write Obsidian notes by filesystem path unless the user explicitly directs that fallback.

### Planning Gate

Do not implement project work unless the active GSD milestone or task has:

- a clear goal
- success criteria
- scoped files, systems, or cluster resources
- verification steps
- relevant project note IDs when available
- an explicit write/approval boundary

If the next milestone is unclear, stop implementation and run a planning/discussion turn instead.

### Obsidian Write Boundary

- Obsidian is readable context through the Obsidian connector/MCP tools.
- Writes to Obsidian should be deliberate and reviewable.
- Ask before substantial note writes.
- When updating Obsidian, follow the vault conventions in `README.md`, relative to the Obsidian vault root.
- Summarize only durable decisions, milestone status, blockers, and next steps back into Obsidian.
- Do not dump raw GSD working state into Obsidian.
- Do not commit `.planning/`.
