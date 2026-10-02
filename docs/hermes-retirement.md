# Hermes retirement (OPS-2)

Status: removal prepared; **stop before merge or production deletion for review**.
This change retires the standing Hermes agent, including ACP/Agmente access,
Camofox, mem0's dedicated database, and the Dograh Hermes voice adapter.
The owner has explicitly chosen to discard all dedicated Hermes data. Backups,
exports, restore tests, retention holds, replacement clients, and archive-lineage
repair are not prerequisites. Git cannot restore deleted volume data.

## GitOps change and protected scope

The Hermes overlay was disabled with `task apps:overlays:disable` and its retired
files removed. The Dograh overlay drops only `hermes-adapter`. The Hermes-only
AppProject destination and Renovate rules are removed. No shared ApplicationSet,
operator, storage class, identity provider, bucket, or credential source changes.

Preserve Dograh API/UI, Asterisk, Jellyseerr adapter and Media Request Assistant,
Dograh Postgres/Valkey/MinIO, all other databases, MetaMCP, media workloads,
Tailscale/tsidp, CNPG operator, ExternalSecrets/onepassword, ZFS CSI, and shared R2
resources. Do not delete the `dograh`, `tailscale`, or `hermes` namespace wholesale.
External callers using Hermes will stop working; no client replacement is planned.
Dograh runtime flow configuration is not represented fully in Git: inspect only
Hermes-specific caller/provider references before cleanup, and do not alter the
Media Request Assistant or shared provider records.

## Deletion inventory

These names are verified in the base manifests. Runtime-generated names and
current ownership must be checked against Bastion immediately before deletion.
No wildcard or prefix-only deletion is authorized by this inventory.

| Namespace | Kind | Exact name(s) |
|---|---|---|
| argocd | Application | `hermes-bastion` (normally removed by ApplicationSet) |
| hermes | Deployment | `hermes`, `hermes-camofox` |
| hermes | Service | `hermes`, `hermes-acp`, `hermes-camofox` |
| hermes | Ingress | `hermes`, `hermes-acp` |
| hermes | ServiceAccount | `hermes` |
| cluster | ClusterRoleBinding | `hermes-view` (preserve shared ClusterRole `view`) |
| hermes | NetworkPolicy | `hermes-gw-ingress`, `hermes-camofox-ingress` |
| hermes | ExternalSecret | `hermes`, `hermes-cnpg-r2` |
| hermes | ScheduledBackup | `hermes-db-backup` |
| hermes | CNPG Cluster | `hermes-db` |
| hermes | ConfigMap | `hermes-acp-config-h5ch2hmg6d` at the base revision; inventory older ACP maps by Argo tracking and pod references |
| dograh | Deployment, Service, ExternalSecret | `dograh-hermes-adapter` |
| dograh | ConfigMap | `dograh-hermes-adapter-config` |
| dograh | Secret | `dograh-hermes-adapter-secret` (owned ESO target) |
| hermes | Secret | `hermes-env`, `hermes-cnpg-r2-secret` (owned ESO targets), `hermes-acp-auth` (separately provisioned) |

CNPG-generated Pods, Services, Secrets, ConfigMaps, monitoring objects and Backup
CRs must be enumerated using the `hermes-db` owner UID, not a global name-prefix
match. Deployment ReplicaSets/Pods and dedicated Tailscale ingress proxies are
controller dependents; let their controllers clean them up and verify the result.
Do not revoke shared provider keys or delete source 1Password items as part of
this Kubernetes cleanup. The names above describe local credential copies only.

### Irreversible dedicated-data set

| Namespace | PVC | Capacity | Data being discarded |
|---|---|---|---|
| hermes | `hermes-data` | 10Gi | Hermes home, sessions/config/auth, ACP state |
| hermes | `hermes-camofox` | 5Gi | Browser profile/state |
| hermes | `hermes-db-1` | 10Gi | Dedicated CNPG mem0 database; generated claim name from latest OPS-2 live inventory |

OPS-2's October 1 live inventory reports all three bound PVs use **Delete** reclaim.
Before deletion record each current PVC UID, bound PV name, PV claimRef UID and
namespace/name, reclaim policy, CSI driver and volumeHandle. Verify every mounted
claim and all database members still belong exclusively to these workloads.
These dynamic PV/CSI identifiers could not be read in this cloud session, so this
is an exact claim-level review set, not permission to guess backend volume names.
Delete the named PVCs only after stopping their consumers; allow CSI to reclaim
only their proven bound volumes. Additional claims, snapshots or changed ownership
require an updated exact inventory. Never issue pool-wide or wildcard ZFS deletes,
strip finalizers, or change the storage class/reclaim policy.

Existing remote archives are not a recovery gate. No R2 object deletion is in this
PR: the shared `restic-backups` bucket and generic credentials remain intact.
If dedicated remote objects are later cleaned up, list and verify their exact
ownership first; do not delete a whole bucket or assume `/hermes/` is exclusively
one format. Do not repair the old `hermes-db` vs `hermes-db-v3` recovery mismatch.

## Execution after the review checkpoint

1. Using already authorized **cloud** access, capture the current Hermes, Dograh,
   media and shared-operator baseline. Check Argo source revisions, sync policies,
   finalizers and operation status; inventory the above resources, dependents and
   PVC/PV identities without reading Secret values or database contents. Compare
   with this inventory. Missing cloud access means pause live work, never use the
   MacBook. Recheck cluster ownership even though data preservation is waived.
2. Review/merge through the normal protected-branch process. Merge is itself a
   deployment boundary: Dograh's automated prune may remove its four adapter
   objects immediately. Keep auto-merge disabled until review is complete.
3. Wait until ApplicationSet has observed the merged removal and no longer
   generates `hermes-bastion`; verify Dograh's desired manifest omits the adapter.
   Do not sync the old Hermes revision or re-enable it. The apps ApplicationSet
   has `preserveResourcesOnDeletion: true`. Latest live evidence reports no Hermes
   resource finalizer. An Application deletion or `--cascade=foreground` alone
   does **not** guarantee deletion of Argo-managed workloads: they are not ordinary
   Kubernetes ownerReference dependents of the Application.
4. Verify adapter pruning in `dograh`; explicitly delete only the listed adapter
   objects if orphaned, including its owned Secret. Remove Hermes Ingresses, stop
   the `hermes` and `hermes-camofox` Deployments, and wait for their Pods to exit.
   Remove `hermes-db-backup` ScheduledBackup, then the dedicated CNPG Cluster;
   wait for database Pods to exit. Delete the three named PVCs only after checking
   the captured claim/PV UID associations. Some may already have been removed by
   their owning controller; confirm their original PV/CSI objects are gone.
5. Explicitly remove the remaining inventoried Hermes Services, NetworkPolicies,
   ExternalSecrets and their local target Secrets, ServiceAccount and
   `hermes-view` binding; remove verified ACP ConfigMaps and `hermes-acp-auth`.
   Check CNPG-owned and Tailscale-owned dependents have been garbage-collected.
   If orphaned, enumerate exact UIDs and ownership before targeted cleanup. Do not
   delete shared Tailscale proxy groups or objects serving other Ingresses.
6. Verify no listed workloads, adapter, database, PVCs or their bound PVs remain,
   no Hermes app can be regenerated, and both Hermes endpoints no longer serve
   Hermes (a cached DNS record or auth error alone is insufficient evidence).
   Verify Dograh API/UI, Asterisk/media request flow and Jellyseerr, other databases,
   MetaMCP, media and shared controllers match baseline health. Lidarr was already
   unavailable in the prior inventory; do not claim that historical condition is
   caused by retirement. Record results in OPS-2 before marking it complete.

Before data deletion, a Git revert can restore definitions (subject to normal
review), but must not blindly recreate a CNPG cluster from the obsolete bootstrap.
After data deletion there is no promised data rollback; recreation is a new,
empty deployment requiring a separate decision.

## Cloud checkpoint evidence

Base: `cdf34b0a`. OPS-2 live reference: comment 10033, approximately
2026-10-01 23:22 UTC; this session has not independently reverified runtime state.
Argo version endpoint is reachable; its application API returns HTTP 401,
`no session information`. The configured Bastion endpoint
`https://talos-master-0:6443/version` returns proxy CONNECT 403. No kubeconfig or
Argo session is available. No credentials retrieved, access grants changed,
production mutations performed, or MacBook tasks used.

Backup PRs #902/#911 remain open and unchanged; ACP PR #1000 is merged. Do not
merge the superseded backup changes as part of retirement.

Validation at the cloud checkpoint: base Hermes render contains 18 objects. Full
Dograh render changes from 32 to 28 objects: only its dedicated adapter Deployment,
Service, ExternalSecret and ConfigMap disappear; all 28 surviving objects are
identical. The only AppProject permission removed is the Hermes destination;
unrelated Renovate rules are identical. Eight existing Argo diff lifecycle tests
and `git diff --check` pass. Public chart repository URLs were blocked: renders
used the pinned Valkey 0.9.4 upstream release and MinIO tenant chart from upstream
operator tag v7.1.1 (6eee6a7caa70555ad009e522ce04861297e9e2be), both cached locally
and excluded from Git. This is local manifest validation, not live health proof.
