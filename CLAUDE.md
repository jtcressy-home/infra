# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a GitOps-based infrastructure repository for a home Kubernetes cluster managed with Talos Linux. The infrastructure follows a layered approach:

- **Cluster Management**: Talos Linux for OS-level Kubernetes cluster management
- **Application Deployment**: ArgoCD for GitOps-based application deployment
- **Infrastructure**: Mix of Kubernetes resources, Kustomize overlays, and Helm charts

## Task Runner Commands

This repository uses **Task** (Taskfile.yml) as the primary build tool. All commands should be run using `task <command>`.

### Essential Commands
- `task -l` - List all available tasks and their descriptions
- `task apps:overlays` - List all ArgoCD application overlays (with optional filters: project, namespace, app, cluster, disabled)
- `task apps:overlays:create project=X namespace=Y app=Z cluster=W` - Create new app overlay
- `task apps:overlays:enable project=X namespace=Y app=Z cluster=W` - Enable disabled overlay
- `task apps:overlays:disable project=X namespace=Y app=Z cluster=W` - Disable overlay
- `task apps:overlays:diff project=X namespace=Y app=Z cluster=W` - Preview changes
- `task apps:overlays:status project=X namespace=Y app=Z cluster=W` - Check ArgoCD app status
- `task talos:ctl -- <args>` - Run talosctl commands with automatic cluster/node selection

### Key Task Categories
- **apps**: ArgoCD application management (create, enable/disable overlays, diff, status)
- **talos**: Talos cluster operations (bootstrap, upgrade, config management)
- **eso**: External Secrets Operator with Doppler integration
- **restic**: Backup operations and snapshot management
- **volsync**: Volume synchronization for persistent storage

## Architecture

### Directory Structure
```
kubernetes/
├── argocd/          # ArgoCD configuration (projects, appsets, static apps)
├── clusters/        # Cluster-specific configurations (currently: bastion)
└── deploy/          # Application deployments organized by project
    ├── admin/       # Administrative tools and operators
    ├── database/    # Database services
    ├── home/        # Home automation and media services
    ├── misc/        # Miscellaneous applications
    ├── monitoring/  # Monitoring and observability stack
    └── system/      # Core system components

.taskfiles/          # Task definitions organized by category
├── apps/           # ArgoCD application management tasks
├── eso/            # External Secrets Operator tasks
├── restic/         # Backup and restore tasks
├── talos/          # Talos cluster management tasks
└── volsync/        # Volume sync tasks

magefiles/          # Go-based build automation (Mage)
```

### Application Overlay System

The `kubernetes/deploy/` directory is monitored by the ArgoCD ApplicationSet `apps` which automatically creates ArgoCD Applications for each overlay found in the directory structure.

#### Directory Structure Pattern
```
kubernetes/deploy/{project}/{namespace}/{app}/
├── clusters/         # Enabled overlays (monitored by ArgoCD)
│   ├── {cluster}/    # Cluster-specific overlay (e.g., "bastion")
│   └── _all/         # Overlay applied to all clusters
└── disabled/         # Disabled overlays (ignored by ArgoCD)
    └── {cluster}/    # Disabled cluster-specific overlay
```

#### ArgoCD ApplicationSet Behavior
The ApplicationSet matches paths:
- `kubernetes/deploy/*/*/*/clusters/*` - Creates individual cluster applications
- `kubernetes/deploy/*/*/*/clusters/_all` - Creates applications for all clusters via matrix generator

Path segments map to ArgoCD Application properties:
- **project**: `{project}` (segment 2) - Maps to ArgoCD AppProject
- **namespace**: `{namespace}` (segment 3) - Target namespace for deployment
- **app**: `{app}` (segment 4) - Application name
- **cluster**: `{cluster}` (segment 6) - Target cluster name

#### Important: Automatic Deletion Behavior

The ApplicationSet is configured with `applicationsSync: sync`, which means:
- **Moving an overlay from `clusters/` to `disabled/` will cause ArgoCD to automatically DELETE the application**
- The application and all its Kubernetes resources will be removed from the cluster
- This happens automatically after the change is merged to the main branch

**Safety Guidelines:**
1. Always use `task apps:overlay:disable` instead of manual `git mv` commands
2. The disable task will show you what resources will be deleted and require confirmation
3. Use `task apps:overlay:status` to check the current state before disabling
4. PR reviews and ArgoCD diff workflow will show deletions before merge
5. To temporarily disable without deleting, consider commenting out in a kustomization instead

**Checking for Orphaned Applications:**
If applications exist in ArgoCD but not in git, use:
```bash
task apps:overlay:orphaned
```

#### Task Command Arguments
Most `task apps:*` commands accept these parameters (can be provided or interactively selected):
- **project**: ArgoCD project name (admin, database, home, misc, monitoring, system)
- **namespace**: Kubernetes namespace for the application
- **app**: Application name within the project/namespace
- **cluster**: Target cluster name, or `_all` for multi-cluster applications

Example overlay paths:
- `kubernetes/deploy/home/media/overseerr/clusters/bastion/` → ArgoCD app `overseerr-bastion`
- `kubernetes/deploy/system/kube-system/multus/clusters/_all/` → ArgoCD app `multus-{cluster}` for each cluster

Each overlay directory contains a `kustomization.yaml` that customizes the base application configuration.

### Key Technologies
- **Talos Linux**: Immutable Kubernetes OS
- **ArgoCD**: GitOps continuous deployment
- **Kustomize**: Kubernetes configuration management
- **External Secrets Operator**: Secret management with Doppler integration
- **Restic**: Backup solution
- **VolSync**: Volume replication for persistence

## Development Workflow

1. **Managing Applications**: Use `task apps:overlays:*` commands to create, enable/disable, and check status of applications
2. **Testing Changes**: Use `task apps:overlays:diff` to preview changes before applying
3. **Cluster Operations**: Use `task talos:*` commands for cluster-level operations
4. **Secrets Management**: Use `task eso:*` commands to manage External Secrets integration

## Go Integration
The repository includes Go modules in `magefiles/` for advanced automation tasks using the Mage build tool. The Go workspace is configured in `go.work` to include the magefiles module.

## Secret Management
Secrets are managed through External Secrets Operator with Doppler as the backend. The `task eso:connect-doppler-branch` command connects Doppler config branches to the Kubernetes cluster.

## Instructions for Claude Code Agent

When you receive a task via `@claude` mention in an issue or pull request comment:

### PR Creation for Code Changes

**Always create a pull request** when your task involves making code changes to the repository. This includes:
- Creating, modifying, or deleting files in `kubernetes/deploy/`
- Updating Kustomize overlays or Helm configurations
- Enabling/disabling application overlays
- Making changes to workflow files or configuration

Use `gh pr create` with:
- A descriptive title that summarizes the change (e.g., "chore(wolf): disable deployment until GPU node available")
- A clear description explaining what was changed and why
- Appropriate commit messages following the repository's conventions

### When NOT to Create a PRs

Only post a comment summary (without a PR) for tasks that don't modify code, such as:
- Informational requests (explaining how something works)
- Status checks (verifying current state)
- Questions about the repository structure

### Code Style and Conventions

Follow the patterns already established in this repository:
- Use the Task runner (`task <command>`) for infrastructure operations
- Respect the overlay system directory structure (clusters/ vs disabled/)
- Maintain the same YAML formatting and comment style as existing files
- Reference the appropriate ArgoCD project for deployments

### Error Handling

If a task requires manual intervention or has blockers, explain what you attempted and what manual steps would be needed, rather than silently failing.