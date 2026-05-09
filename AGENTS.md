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

- GSD is the local planning/execution loop for scoped infra-repo work.
- `.planning/` is private operational state for the current worktree and is mounted as a private git submodule.
- Obsidian is the preferred durable curated project record when a project has Obsidian notes.
- Codex is the bounded execution harness for code, GitOps, and infra edits.

### GSD Private Submodule

- `.planning/` is a private submodule at `https://github.com/jtcressy-home/infra-planning.git`.
- The public `infra` repo should track only `.gitmodules` and the `.planning` gitlink, not private planning file contents.
- Local GSD routing files such as `.planning/active-workstream` and generated root `.planning/STATE.md` mirrors are private submodule working-tree state and should not be committed.
- If `.planning/` is missing after clone, initialize it with `git submodule update --init .planning` using credentials that can read the private repo.
- If private submodule access is unavailable, do not recreate `.planning/` in the public repo. Ask the user to initialize/authorize the submodule or provide an explicit fallback.

### Active Project Rule

- Each worktree has one atomic `.planning/` submodule, which may contain multiple GSD workstreams.
- Treat unrelated infra efforts as separate GSD workstreams under `.planning/workstreams/<name>/`, or use separate git worktrees when that is cleaner.
- Do not mix unrelated projects in one flat roadmap/state file.
- If `.planning/` already exists, infer repo-wide context from `.planning/PROJECT.md` and the active project from the current workstream. Prefer `gsd-sdk query workstream.list` and `gsd-sdk query workstream.status <name>` when workstreams are present.
- If `.planning/` does not exist, ask the user which Obsidian project folder should be used as the durable record before starting GSD planning.
- Use vault-root-relative Obsidian paths only, such as `openclaw/index.md` or `some-project/index.md`.
- Do not use absolute filesystem paths for Obsidian notes in instructions, plans, or summaries.

### Project Switching

- Before switching projects in the same worktree, preserve the current workstream state in the private `.planning` submodule. If the workstream is Obsidian-backed, sync durable decisions, milestone status, blockers, and next steps back to the appropriate Obsidian project notes first.
- After any required sync, ask the user whether to keep, archive, or leave the old workstream state in place before starting another project.
- Prefer a separate git worktree for each active GSD project when practical.
- A worktree may serve as the durable local workspace for that project's private `.planning` submodule state while it exists.
- Before deleting, closing, or abandoning a worktree, ensure private planning state has been committed to the private submodule when it should be retained. If the project is Obsidian-backed, also sync durable decisions, milestone status, blockers, and next steps back to Obsidian.

### Obsidian Access

- Use the Obsidian connector/MCP tools for Obsidian reads and writes when planning depends on Obsidian notes.
- Before starting or substantially reshaping an Obsidian-backed project, read the selected project's Obsidian index note and its linked current working set.
- If Obsidian connector/MCP tools are unavailable for Obsidian-backed planning, stop and ask the user to repair the Obsidian connection or explicitly authorize a non-Obsidian fallback.
- Existing GSD workstreams may be inspected and resumed from `.planning/` without Obsidian when the local state has enough context for the requested bounded work. Record that any Obsidian sync is deferred rather than silently writing filesystem-vault notes.
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
- Do not commit private `.planning/` contents to the public repo. Only update the public `.planning` submodule pointer when deliberately advancing the private planning repo revision.
