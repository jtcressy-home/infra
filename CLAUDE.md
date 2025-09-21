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