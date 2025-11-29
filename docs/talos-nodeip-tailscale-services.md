# Talos NodeIP Configuration and Tailscale Services

## Overview

This document describes the configuration changes to use underlay network IPs for node-to-node communication while keeping Tailscale as a sidecar utility, and the implementation of Tailscale services for Kubernetes API load-balancing.

## Problem Statement

The previous configuration used Tailscale IPs (100.x.x.x CGNAT range) as the primary NodeIP for all node-to-node communication. This caused several issues:

1. **Network path complexity**: Traffic would bounce between Tailscale extension, Cilium, Tailscale container, services, and back - entering/exiting the overlay multiple times
2. **Performance degradation**: Applications using Tailscale funnels via the k8s operator experienced terrible performance due to this multi-hop path
3. **Unnecessary overhead**: For nodes on the same physical network, using an overlay for primary communication adds latency

## Solution

### NodeIP Configuration Change

Changed the kubelet NodeIP configuration to use underlay network IPs (192.168.20.0/24) instead of Tailscale IPs.

**Benefits**:
- Direct node-to-node communication on the underlay network
- Reduced latency and improved performance
- Tailscale becomes a sidecar utility rather than the primary network path
- Simpler network troubleshooting

**Changes Made**:
1. **kubelet.nodeIP.validSubnets**: `100.64.0.0/10` → `192.168.20.0/24`
2. **etcd.advertisedSubnets**: `100.64.0.0/10` → `192.168.20.0/24`
3. **network.nameservers**: `100.100.100.100` → `192.168.20.1, 1.1.1.1`

### Tailscale Services for K8s API Load-Balancing

Implemented Tailscale serve configuration on control plane nodes to provide load-balanced access to the Kubernetes API.

**How It Works**:
- Each control plane node runs `tailscale serve` to expose port 6443
- Tailscale automatically load-balances connections across all healthy nodes
- Clients can connect to a stable service name instead of individual node addresses
- Similar to Tailscale's implementation for Proxmox clusters

**Implementation**:
Added to control plane `extensionServices`:
```yaml
- TS_SERVE_CONFIG=/etc/tailscale/serve.json
files:
  - content: |
      {
        "TCP": {
          "6443": {
            "HTTPS": true
          }
        }
      }
    path: /etc/tailscale/serve.json
    permissions: "0644"
```

**Benefits**:
- Built-in load balancing across all control plane nodes
- Automatic health checking and failover
- No need for external load balancer (HAProxy, kube-vip, etc.)
- Simplified API endpoint management
- Consistent with existing Proxmox setup

## Configuration Details

### Before (Tailscale as Primary Network)

```yaml
kubelet:
  nodeIP:
    validSubnets:
      - 100.64.0.0/10  # Tailscale CGNAT range

etcd:
  advertisedSubnets:
    - 100.64.0.0/10

network:
  nameservers:
    - 100.100.100.100  # Tailscale DNS
```

### After (Underlay as Primary, Tailscale as Sidecar)

```yaml
kubelet:
  nodeIP:
    validSubnets:
      - 192.168.20.0/24  # Underlay network

etcd:
  advertisedSubnets:
    - 192.168.20.0/24

network:
  nameservers:
    - 192.168.20.1  # Local gateway
    - 1.1.1.1       # Cloudflare DNS fallback
```

### Control Plane Tailscale Serve

```yaml
controlPlane:
  extensionServices:
    - name: tailscale
      environment:
        - TS_SERVE_CONFIG=/etc/tailscale/serve.json
      files:
        - content: |
            {
              "TCP": {
                "6443": {
                  "HTTPS": true
                }
              }
            }
          path: /etc/tailscale/serve.json
```

## Applying the Changes

### Prerequisites

1. Ensure all nodes have connectivity on the 192.168.20.0/24 network
2. Verify DNS resolution works for node hostnames
3. Backup current Talos configuration

### Steps

1. **Generate new configurations**:
   ```bash
   task talos:genconfig
   ```

2. **Apply to control plane nodes sequentially**:
   ```bash
   # Apply to first control plane node
   task talos:apply-config node=talos-master-0

   # Wait for node to be healthy
   kubectl get nodes -w

   # Repeat for other control plane nodes
   task talos:apply-config node=talos-master-1
   task talos:apply-config node=talos-master-2
   ```

3. **Apply to worker nodes**:
   ```bash
   task talos:apply-config node=talos-worker-gpu-0
   task talos:apply-config node=talos-worker-gpu-1
   ```

4. **Verify connectivity**:
   ```bash
   # Check node IPs
   kubectl get nodes -o wide

   # Should show 192.168.20.x addresses

   # Test API access via Tailscale service
   kubectl --server=https://bastion-k8s.tailnet-4d89.ts.net:6443 get nodes
   ```

### Verification

1. **Node IPs**: Verify nodes are using 192.168.20.x addresses
   ```bash
   kubectl get nodes -o wide
   ```

2. **etcd health**: Ensure etcd cluster is healthy
   ```bash
   task talos:ctl -- etcd members
   ```

3. **Inter-node communication**: Test pod-to-pod communication across nodes
   ```bash
   kubectl run test-1 --image=alpine -- sleep 3600
   kubectl run test-2 --image=alpine -- sleep 3600
   # Exec into pods and ping each other
   ```

4. **Tailscale serve status**: Check if API is being served
   ```bash
   task talos:ctl -- service tailscale status
   ```

5. **API load balancing**: Connect to the Tailscale service endpoint
   ```bash
   kubectl --server=https://bastion-k8s.tailnet-4d89.ts.net:6443 get nodes
   ```

## Rollback Procedure

If issues occur, revert the configuration:

1. **Update talconfig.yaml** to use original values:
   ```yaml
   kubelet:
     nodeIP:
       validSubnets:
         - 100.64.0.0/10

   etcd:
     advertisedSubnets:
       - 100.64.0.0/10

   network:
     nameservers:
       - 100.100.100.100
   ```

2. **Remove Tailscale serve config** from control plane nodes

3. **Regenerate and apply**:
   ```bash
   task talos:genconfig
   task talos:apply-config node=<node-name>
   ```

## Impact on Existing Applications

### Unaffected

- **Application-level Tailscale ingress**: Apps using `*.tailnet-4d89.ts.net` ingress via the Tailscale operator are unaffected
- **Tailscale funnels**: Should see improved performance as network path is simplified
- **External access**: Access from outside the cluster via Tailscale remains unchanged

### Potentially Affected

- **Services binding to specific IPs**: Any services hardcoded to bind to Tailscale IPs will need updates
- **NetworkPolicies**: Policies referencing 100.64.0.0/10 range need updating to 192.168.20.0/24
- **Monitoring**: Prometheus targets or other monitoring may need IP updates

## Future Enhancements

1. **Update API endpoint**: Consider updating `endpoint` in talconfig.yaml to use the Tailscale service name:
   ```yaml
   endpoint: https://bastion-k8s.tailnet-4d89.ts.net:6443
   ```

2. **Service naming**: Configure a custom Tailscale funnel name for the k8s API service

3. **Monitoring**: Add monitoring for Tailscale serve status and connection distribution

4. **Multi-cluster**: Extend this pattern to other clusters in the infrastructure

## References

- [Tailscale Serve Documentation](https://tailscale.com/kb/1312/serve)
- [Talos Extension Services](https://www.talos.dev/v1.8/talos-guides/configuration/extension-services/)
- [Kubernetes Node IPs](https://kubernetes.io/docs/concepts/architecture/nodes/)
