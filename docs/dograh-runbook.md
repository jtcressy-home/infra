# Dograh Runbook

## Dograh Deployment Inputs

Dograh v1 is one ArgoCD-discovered app under `kubernetes/deploy/home/dograh/dograh/clusters/bastion` in namespace `dograh`.

Primary local commands:

```bash
task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion
task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion > /tmp/dograh-full-render.yaml
kubectl apply --dry-run=server -f /tmp/dograh-full-render.yaml
task apps:overlays:status project=home namespace=dograh app=dograh cluster=bastion
```

Public and internal endpoints:

```text
Dograh UI/API=https://dograh.tailnet-4d89.ts.net
PUBLIC_BASE_URL=https://dograh.tailnet-4d89.ts.net
MINIO_PUBLIC_ENDPOINT=https://dograh-minio.tailnet-4d89.ts.net
Dograh ARI endpoint=http://dograh-asterisk.dograh.svc.cluster.local:8088
Asterisk websocket URI=ws://dograh-api.dograh.svc.cluster.local:8000/api/v1/telephony/ws/ari
```

Runtime pins and LAN inputs:

```text
DOGRAH_API_IMAGE=ghcr.io/dograh-hq/dograh-api:1.29.0@sha256:f338d55d56acad6e8ef4054aa8d0bc5d74884f3418bbe24d54235d2378a3fdbe
DOGRAH_UI_IMAGE=ghcr.io/dograh-hq/dograh-ui:1.29.0@sha256:54da6c9877dcdae1d0c37aa4c28a7ba1689dc44a484508f7b1c47b1f2c133deb
Asterisk image=ghcr.io/jtcressy/docker-asterisk:asterisk-22.9.0@sha256:984a02847c8fd9963b20dacdfb14be21e420b278914870ad14c5871eca0b5df7
Asterisk image source=https://github.com/jtcressy/docker-asterisk
Multus MAC=02:8c:20:0c:1a:01
Multus IP=192.168.20.11
direct-L2 bind=ASTERISK_PJSIP_BINDADDR=192.168.20.11
Stasis app=dograh
websocket client=dograh
extension 7000
```

Static credentials are stored in the `dograh` 1Password item and delivered through ExternalSecrets. Do not print or paste secret values into tickets, docs, manifests, or validation notes.

Required 1Password-backed fields are `POSTGRES_USER`, `POSTGRES_PASS`, `POSTGRES_PASSWORD`, `POSTGRES_SUPER_PASS`, `VALKEY_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `OSS_JWT_SECRET`, `ASTERISK_ARI_PASSWORD`, `UNIFI_TALK_SIP_SERVER`, `UNIFI_TALK_SIP_USERNAME`, `UNIFI_TALK_SIP_PASSWORD`, and `UNIFI_TALK_SIP_EXTENSION`. Shared Cloudflare R2 credentials stay in the `cloudflare-r2-generic` item and are referenced by field name only.

## Initial Admin Access

Open Dograh through the tailnet URL:

```text
https://dograh.tailnet-4d89.ts.net
```

Use the local Dograh bootstrap flow to create the initial admin account after the API and UI are healthy. The admin credential is app-local state; do not store it in Git or in this runbook.

Minimum access checks:

```bash
kubectl -n dograh rollout status deploy/dograh-api deploy/dograh-ui
kubectl -n dograh get deploy dograh-api dograh-ui
kubectl -n dograh get svc dograh-api dograh-ui
kubectl -n dograh logs deploy/dograh-api --tail=100
kubectl -n dograh logs deploy/dograh-ui --tail=100
```

The API health endpoint is exposed through the UI/API host under `/api/v1/health` after Tailscale ingress is synced.

## Authentication Posture

Dograh v1 uses `AUTH_PROVIDER=local` because generic OIDC/tsidp support was not found in the current Dograh runtime. Tailscale ingress keeps the UI/API private to the tailnet, but Dograh authentication remains Dograh-local.

Operational expectations:

- Treat tailnet access as the network boundary and Dograh local auth as the application boundary.
- Do not add tsidp or other OIDC settings unless Dograh gains a supported generic OIDC provider.
- Do not enable public Funnel for this app.
- Rotate the app-local admin credential through Dograh, not through GitOps.

## Telephony Provider Setup

Asterisk runs as the separate `dograh-asterisk` workload. The image source is `https://github.com/jtcressy/docker-asterisk`, and the pinned image is:

```text
ghcr.io/jtcressy/docker-asterisk:asterisk-22.9.0@sha256:984a02847c8fd9963b20dacdfb14be21e420b278914870ad14c5871eca0b5df7
```

The default network model is direct L2 through Multus/macvlan:

```text
Multus network=kube-system/macvlan-conf-dhcp
interface=eth1
MAC=02:8c:20:0c:1a:01
LAN IP=192.168.20.11
ASTERISK_PJSIP_BINDADDR=192.168.20.11
```

Do not use `hostNetwork`, `hostPort`, NodePort, localhost, or `host.docker.internal` for the v1 SIP/RTP path. NAT fields such as local net, external signaling address, and external media address are fallback-only settings if direct L2 fails with evidence.

UniFi Talk SIP credentials are reused from the previous OpenClaw Voice setup through the `dograh` 1Password item by default. New UniFi Talk credential provisioning through browser automation is only needed if legacy credential reuse fails.

Dograh ARI provider settings:

```text
ARI Endpoint URL=http://dograh-asterisk.dograh.svc.cluster.local:8088
ARI username=dograh
Stasis app=dograh
WebSocket client name=dograh
Phone number or extension=7000
```

The ARI password comes from the `dograh` 1Password item and must match the Asterisk environment. The Asterisk websocket client connects inward to Dograh at:

```text
ws://dograh-api.dograh.svc.cluster.local:8000/api/v1/telephony/ws/ari
```

Provider checks:

```bash
kubectl -n dograh get pod -l app.kubernetes.io/name=dograh-asterisk -o jsonpath='{.items[0].metadata.annotations.k8s\.v1\.cni\.cncf\.io/network-status}'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'core show version'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'module show like chan_websocket'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'module show like res_websocket_client'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'module show like res_ari'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'module show like res_pjsip'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'http show status'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'pjsip show registrations'
```

## No-Tool Test Workflow

The v1 no-tool workflow is infrastructure validation only, not the full Media Request Assistant per D-03. It should answer the inbound call, converse briefly, and prove that Dograh receives caller audio and returns model audio through Asterisk.

Configure the workflow inside Dograh after the app is healthy:

```text
Workflow purpose=real inbound call infrastructure validation
Tools=none
Assigned telephony provider=Asterisk ARI
Assigned phone number or extension=7000
Expected behavior=brief spoken response without external tool calls
```

Do not add external media tooling, request tooling, or application-specific smoke cases to this v1 workflow.

## Health And Logs

Overlay and ArgoCD checks:

```bash
task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=home namespace=dograh app=dograh cluster=bastion
kubectl -n dograh get all
```

API/UI checks:

```bash
kubectl -n dograh rollout status deploy/dograh-api deploy/dograh-ui
kubectl -n dograh get deploy dograh-api dograh-ui
kubectl -n dograh get svc dograh-api dograh-ui
kubectl -n dograh logs deploy/dograh-api --tail=100
kubectl -n dograh logs deploy/dograh-ui --tail=100
```

Database, cache, and object storage checks:

```bash
kubectl -n dograh get cluster dograh-db
kubectl -n dograh get scheduledbackup dograh-db-backup
kubectl -n dograh get deploy dograh-valkey
kubectl -n dograh get tenant dograh-minio
kubectl -n dograh get cronjob dograh-minio-r2-backup
```

Asterisk checks:

```bash
kubectl -n dograh rollout status deploy/dograh-asterisk
kubectl -n dograh logs deploy/dograh-asterisk --tail=100
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'core show version'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'http show status'
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'pjsip show registrations'
```

## Backup And Restore

CNPG database backups target Cloudflare R2 through the Dograh database backup resources. Confirm the CNPG cluster and scheduled backup exist:

```bash
kubectl -n dograh get cluster dograh-db
kubectl -n dograh get scheduledbackup dograh-db-backup
kubectl -n dograh describe scheduledbackup dograh-db-backup
```

Database restore uses CloudNativePG recovery from the R2 backup destination. Perform restore as a planned change with a separate manifest/update, preserve the current cluster until the recovery target is verified, and avoid printing database credentials.

MinIO stores Dograh voice audio in the `voice-audio` bucket. Object-level backup copies objects to the Cloudflare R2 bucket/prefix `dograh-voice-audio` without delete propagation. Confirm the backup job:

```bash
kubectl -n dograh get tenant dograh-minio
kubectl -n dograh get cronjob dograh-minio-r2-backup
kubectl -n dograh create job --from=cronjob/dograh-minio-r2-backup dograh-minio-r2-backup-manual
kubectl -n dograh logs job/dograh-minio-r2-backup-manual
```

MinIO object restore from R2 bucket/prefix `dograh-voice-audio` should copy objects back into local `voice-audio` after the Tenant is healthy. Use MinIO client aliases backed by Kubernetes secrets; do not include access keys in command history or docs.

Valkey is disposable runtime state. If Valkey is lost, restart Dograh API workers after Valkey returns and allow queues/session cache to rebuild.

Asterisk `/var/lib/asterisk`, `/var/log/asterisk`, and `/var/spool/asterisk` are intentionally non-durable for v1. Asterisk voicemail, recordings, and spool contents are not protected unless the user later requests voicemail or recording durability.

## Rollback And Cutover

Before cutover:

```bash
task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=home namespace=dograh app=dograh cluster=bastion
kubectl -n dograh rollout status deploy/dograh-api deploy/dograh-ui deploy/dograh-asterisk
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'pjsip show registrations'
```

Cutover is only complete after the no-tool workflow is assigned to extension `7000` and a real inbound call passes. Keep the previous UniFi/OpenClaw Voice path available until the Dograh call path is proven.

Rollback options:

- Revert the Dograh GitOps commit if the overlay change is the cause.
- Re-sync ArgoCD after revert and verify app health with the task status wrapper.
- Return UniFi Talk routing to the previous known-good target if Asterisk registration or two-way audio fails.
- Preserve CNPG and MinIO data while investigating unless a deliberate restore plan has been approved.

Do not move the overlay to `disabled/` manually. Use the repo overlay tasks for app lifecycle operations.

## Real Inbound Call Validation

This section is the operator checklist for Task 3 live validation. Do not mark it complete from local render checks alone.

Pre-call checks:

```bash
task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=home namespace=dograh app=dograh cluster=bastion
kubectl -n dograh rollout status deploy/dograh-api deploy/dograh-ui deploy/dograh-asterisk
kubectl -n dograh get cluster dograh-db
kubectl -n dograh get tenant dograh-minio
kubectl -n dograh get cronjob dograh-minio-r2-backup
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'pjsip show registrations'
```

Call UAT:

```text
1. Confirm Dograh ARI provider uses http://dograh-asterisk.dograh.svc.cluster.local:8088.
2. Confirm Stasis app dograh, websocket client dograh, and extension 7000 are configured.
3. Confirm the no-tool workflow is assigned to extension 7000.
4. Place a real inbound UniFi Talk call.
5. Confirm Dograh hears caller audio.
6. Confirm the caller hears Dograh's model response.
7. Record pass/fail evidence without secret values.
```
