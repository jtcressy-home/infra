# Hermes retirement

Status: prepared for review. Do not merge, deploy or delete production resources
until the execution checkpoint is approved and current ownership is verified.

## Scope

Remove the Hermes overlay, its dedicated Dograh adapter, the Hermes AppProject
destination and Hermes-specific update rules. Preserve the current Dograh version
and all unrelated application, operator, storage and identity configuration.

The dedicated Hermes data is to be discarded. Backup/export/restore tests,
retention holds, replacement clients and archive repair are not prerequisites.
Deleting persistent data is irreversible; a Git revert cannot restore it.

## Manifest inventory

| Namespace | Kind | Name |
|---|---|---|
| argocd | Application | `hermes-bastion` |
| hermes | Deployment | `hermes`, `hermes-camofox` |
| hermes | Service | `hermes`, `hermes-acp`, `hermes-camofox` |
| hermes | Ingress | `hermes`, `hermes-acp` |
| hermes | ServiceAccount | `hermes` |
| cluster | ClusterRoleBinding | `hermes-view` |
| hermes | NetworkPolicy | `hermes-gw-ingress`, `hermes-camofox-ingress` |
| hermes | ExternalSecret | `hermes`, `hermes-cnpg-r2` |
| hermes | ScheduledBackup | `hermes-db-backup` |
| hermes | CNPG Cluster | `hermes-db` |
| hermes | ConfigMap | generated `hermes-acp-config` |
| hermes | PVC | `hermes-data` (10Gi), `hermes-camofox` (5Gi) |
| dograh | Deployment, Service, ExternalSecret | `dograh-hermes-adapter` |
| dograh | ConfigMap | `dograh-hermes-adapter-config` |

Inventory generated database claims, local Secret targets, controller dependents
and ingress proxies by exact ownership before cleanup. Record current resource
UIDs, PVC/PV claim references, reclaim policies and CSI identities in the private
execution record. Do not infer ownership from names or delete by prefix.

## Execution checkpoint

1. Capture current ownership, Argo source revision/sync policy/finalizers, and the
   protected-service health baseline. Do not read Secret values or database data.
2. Obtain review approval before merge. Merge is a deployment boundary: automated
   pruning can remove the four dedicated Dograh adapter objects immediately.
3. Verify ApplicationSet no longer generates Hermes. Its resource-preservation
   policy can leave workloads behind; Application deletion alone is insufficient.
4. After separate production-cleanup approval, remove only verified dedicated
   resources. Stop workload and database consumers before deleting their claims.
   Verify the corresponding volumes and controller dependents are reclaimed.
5. Preserve Dograh API/UI, Asterisk, Jellyseerr/media-request flows, other databases,
   media applications, MetaMCP and all shared operators, identity services, storage
   classes, credential sources and backup buckets. Do not delete namespaces,
   shared remote objects, or shared credentials; do not strip finalizers.
6. Verify Hermes cannot be regenerated and protected services match the baseline.
   Record completion only after live verification. Recreation after data deletion
   would be a separate decision for a new empty deployment.

## Local validation

The current base renders 18 Hermes objects and four dedicated Dograh adapter
objects. All eight existing Argo diff lifecycle tests and `git diff --check` pass.
The proposed removal applies cleanly to the current base and preserves unrelated
files, including the newer Dograh and Terraform updates. Live ownership and the
protected-service baseline remain execution prerequisites; local validation does
not establish production readiness.
