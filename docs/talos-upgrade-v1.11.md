# Talos Linux Upgrade to v1.11.x

This document provides a step-by-step guide for upgrading the Talos Linux cluster from v1.8.3 to v1.11.x, including Kubernetes upgrade from v1.30.3 to v1.34.x and Cilium upgrade from v1.16.3 to v1.18.x.

## Current State
- Talos: v1.8.3
- Kubernetes: v1.30.3
- Cilium: v1.16.3
- Cluster: bastion (3 control-plane nodes)

## Target State
- Talos: v1.11.5+
- Kubernetes: v1.34.x
- Cilium: v1.18.x

## Prerequisites

### 1. Complete Issue #426
⚠️ **BLOCKER**: Issue #426 (Remove Tailscale underlay networking) must be completed first as it affects network configuration.

### 2. Backup Preparation
Before starting the upgrade, ensure all backups are current:

```bash
# Backup etcd
task talos:ctl cluster=bastion -- etcd snapshot

# Verify Restic backups are current
task restic:snapshots

# Backup Talos configuration
cp -r kubernetes/clusters/bastion/talos kubernetes/clusters/bastion/talos.backup-$(date +%Y%m%d)
```

### 3. Review Release Notes
Manually review the following release notes for breaking changes:
- [Talos v1.9.0 Release Notes](https://github.com/siderolabs/talos/releases/tag/v1.9.0)
- [Talos v1.10.0 Release Notes](https://github.com/siderolabs/talos/releases/tag/v1.10.0)
- [Talos v1.11.0 Release Notes](https://github.com/siderolabs/talos/releases/tag/v1.11.0)
- [Cilium v1.18.x Release Notes](https://github.com/cilium/cilium/releases)

## Upgrade Strategy

### Option 1: Incremental Upgrade (Recommended for Production)
Upgrade through each minor version: v1.8 → v1.9 → v1.10 → v1.11

**Pros:**
- Lower risk, easier to identify issues
- Can stop at any version if problems occur
- Better tested upgrade path

**Cons:**
- Takes longer (requires 3 upgrade cycles)
- More manual intervention

### Option 2: Direct Upgrade
Skip directly from v1.8 to v1.11

**Pros:**
- Faster completion
- Fewer steps

**Cons:**
- Higher risk
- Harder to troubleshoot if issues occur
- May miss version-specific migration steps

**Recommendation:** Use Option 1 (Incremental) unless you have a strong reason for Option 2.

## Upgrade Procedure

### Phase 1: Pre-Flight Checks

```bash
# Check cluster health
task talos:ctl cluster=bastion -- health

# Check node status
kubectl get nodes -o wide

# Check critical workloads
kubectl get pods -A | grep -v Running

# Verify ArgoCD sync status
kubectl get applications -n argocd
```

### Phase 2: Update Configuration Files

The configuration files have been updated in this PR:
- `kubernetes/clusters/bastion/talos/talconfig.yaml` - Talos and Kubernetes versions
- `kubernetes/clusters/bastion/cni/kustomization.yaml` - Cilium version

### Phase 3: Cilium Upgrade (Do This First!)

Cilium should be upgraded before Talos to ensure CNI compatibility.

```bash
# The Cilium upgrade will be applied via GitOps after merging this PR
# Monitor the upgrade:
kubectl -n kube-system rollout status daemonset/cilium

# Verify Cilium health
kubectl -n kube-system exec -ti ds/cilium -- cilium status
```

**Security Note:** Cilium v1.18.x includes a fix for GHSA-38pp-6gcp-rqvm. Verify this is applied after upgrade.

### Phase 4: Talos Upgrade (Incremental Path)

#### Step 1: Upgrade to v1.9.x

```bash
# Update talconfig.yaml to v1.9.x
# Generate new configs
task talos:genconfig cluster=bastion

# Upgrade control plane nodes one at a time
task talos:upgrade-talos cluster=bastion node=talos-master-0
# Wait for node to be Ready
kubectl wait --for=condition=Ready node/talos-master-0 --timeout=10m

task talos:upgrade-talos cluster=bastion node=talos-master-1
kubectl wait --for=condition=Ready node/talos-master-1 --timeout=10m

task talos:upgrade-talos cluster=bastion node=talos-master-2
kubectl wait --for=condition=Ready node/talos-master-2 --timeout=10m

# Upgrade worker nodes
task talos:upgrade-talos cluster=bastion node=talos-worker-gpu-0
kubectl wait --for=condition=Ready node/talos-worker-gpu-0 --timeout=10m

task talos:upgrade-talos cluster=bastion node=talos-worker-gpu-1
kubectl wait --for=condition=Ready node/talos-worker-gpu-1 --timeout=10m

# Verify cluster health
task talos:ctl cluster=bastion -- health
```

#### Step 2: Upgrade to v1.10.x

Repeat the process above after updating talconfig.yaml to v1.10.x.

#### Step 3: Upgrade to v1.11.x

Repeat the process above after updating talconfig.yaml to v1.11.x.

### Phase 5: Kubernetes Upgrade

After Talos is on v1.11.x, upgrade Kubernetes:

```bash
# Update talconfig.yaml to Kubernetes v1.34.x
task talos:genconfig cluster=bastion

# Apply the config update
task talos:apply cluster=bastion nodes=talos-master-0,talos-master-1,talos-master-2

# Upgrade Kubernetes
task talos:upgrade-k8s cluster=bastion node=talos-master-0

# Verify upgrade
kubectl version
kubectl get nodes
```

### Phase 6: Post-Upgrade Validation

```bash
# Check all nodes
kubectl get nodes -o wide

# Check system pods
kubectl get pods -A

# Check ArgoCD applications
kubectl get applications -n argocd

# Verify Cilium
kubectl -n kube-system exec -ti ds/cilium -- cilium status

# Check monitoring stack
kubectl get pods -n monitoring

# Run health checks
task talos:ctl cluster=bastion -- health

# Verify etcd cluster
task talos:ctl cluster=bastion -- etcd members
```

## Alternative: System Upgrade Controller (Automated)

The cluster has System Upgrade Controller configured. After configuration is updated, you can use SUC for automated upgrades:

```bash
# The SUC plan is at: kubernetes/deploy/system/system-upgrade/suc-plans/
# Update the TALOS_VERSION in the overlay
# SUC will automatically roll through nodes with the new version
```

⚠️ **Warning:** SUC automates the process but provides less control. Use manual upgrade for major version jumps.

## Rollback Plan

If issues occur during upgrade:

1. **Before completing all nodes:** Stop the upgrade, nodes on older versions can coexist temporarily
2. **After upgrade completes:** Rollback requires:
   - Restore etcd from backup
   - Reinstall previous Talos version
   - Restore previous configurations

## Troubleshooting

### Common Issues

1. **Node won't upgrade:** Check connectivity, verify image availability
2. **Pods not starting:** Check CNI health, node taints
3. **etcd unhealthy:** Verify networking, check quorum
4. **ArgoCD sync issues:** May need to refresh/hard refresh applications

### Emergency Contacts

- Talos Community: [Slack](https://slack.dev.talos-systems.io/)
- Documentation: https://www.talos.dev/

## Timeline Estimate

- **Incremental Path (Recommended):** Plan for 2-4 hour maintenance window
  - Cilium upgrade: 30 minutes
  - Each Talos version upgrade: 45-60 minutes
  - Kubernetes upgrade: 30 minutes
  - Validation: 30 minutes

- **Direct Path (Not Recommended):** 1-2 hours
  - Higher risk of issues requiring troubleshooting

## Post-Upgrade Tasks

- [ ] Update documentation with any configuration changes
- [ ] Close Renovate PRs (#342, #326, #354)
- [ ] Update this repository's README if version references exist
- [ ] Verify all applications are synced and healthy
- [ ] Create new etcd backup after successful upgrade
