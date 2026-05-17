# CLAUDE.md

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

## Explore First

Analyze the repo with Explore before making changes. Follow existing patterns for directory structure, YAML style, and naming conventions.

## GSD Project Loop

This repo may use official upstream GSD for scoped infra-repo planning and execution.

### Roles

- GSD is the local planning/execution loop for scoped infra-repo work.
- `.planning/` is private operational state for the current worktree and is mounted as a private git submodule.
- Obsidian can be used as source material for bootstrap or explicit sync, but `.planning/` is sufficient operational state after ingest.
- Codex is the bounded execution harness for code, GitOps, and infra edits.

### GSD Private Submodule

- `.planning/` is a private submodule at `https://github.com/jtcressy-home/infra-planning.git`.
- The public `infra` repo should track only `.gitmodules` and the `.planning` gitlink, not private planning file contents.
- Local GSD routing files such as `.planning/active-workstream` and generated root `.planning/STATE.md` mirrors are private submodule working-tree state and should not be committed.
- If `.planning/` is missing or empty after clone, check `.gitmodules` first and initialize it with `git submodule update --init .planning` using credentials that can read the private repo.
- If `.planning/` exists as a submodule, check `git submodule status .planning` before assuming planning state is absent or stale.
- If private submodule access is unavailable, do not recreate `.planning/` in the public repo. Ask the user to initialize/authorize the submodule or provide an explicit fallback.

### Active Project Rule

- Each worktree has one atomic `.planning/` submodule, which may contain multiple GSD workstreams.
- Treat unrelated infra efforts as separate GSD workstreams under `.planning/workstreams/<name>/`, or use separate git worktrees when that is cleaner.
- Do not mix unrelated projects in one flat roadmap/state file.
- If `.planning/` already exists, infer repo-wide context from `.planning/PROJECT.md` and the active project from the current workstream. Prefer `gsd-sdk query workstream.list` and `gsd-sdk query workstream.status <name>` when workstreams are present.
- If `.planning/` does not exist or does not contain expected GSD files, first treat it as an uninitialized or out-of-sync submodule and follow the GSD Private Submodule checks above. Only ask whether to initialize from Obsidian, another planning source, or a blank GSD project after confirming the private submodule cannot provide existing state.
- When using Obsidian paths, use vault-root-relative paths only, such as `openclaw/index.md` or `some-project/index.md`.
- Do not use absolute filesystem paths for Obsidian notes in instructions, plans, or summaries unless the user explicitly requests that fallback.

### Project Switching

- Before switching projects in the same worktree, preserve the current workstream state in the private `.planning` submodule when it should be retained.
- Ask the user whether to keep, archive, or leave the old workstream state in place before starting another project.
- Prefer a separate git worktree for each active GSD project when practical.
- A worktree may serve as the durable local workspace for that project's private `.planning` submodule state while it exists.
- Before deleting, closing, or abandoning a worktree, ensure private planning state has been committed to the private submodule when it should be retained.

### Obsidian Access

- Use the Obsidian connector/MCP tools when the user explicitly asks to ingest from, read, or update Obsidian.
- After Obsidian has been ingested into `.planning/`, continue from `.planning/` unless the user asks to refresh or sync Obsidian.
- If Obsidian connector/MCP tools are unavailable for an explicit Obsidian task, stop and ask the user to repair the Obsidian connection or explicitly authorize a non-Obsidian fallback.
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

- Obsidian writes are optional sync actions, not a default lifecycle requirement.
- Ask before substantial note writes.
- When updating Obsidian, follow the vault conventions in `README.md`, relative to the Obsidian vault root.
- Summarize only durable decisions, milestone status, blockers, and next steps back into Obsidian.
- Do not dump raw GSD working state into Obsidian.
- Do not commit private `.planning/` contents to the public repo. Only update the public `.planning` submodule pointer when deliberately advancing the private planning repo revision.
