# Dograh Runbook

## Dograh Deployment Inputs

Dograh v1 is one ArgoCD-discovered app under `kubernetes/deploy/agentic-ai/dograh/dograh/clusters/bastion` in namespace `dograh`.

Primary local commands:

```bash
task apps:overlays:render project=agentic-ai namespace=dograh app=dograh cluster=bastion
task apps:overlays:render project=agentic-ai namespace=dograh app=dograh cluster=bastion > /tmp/dograh-full-render.yaml
kubectl apply --dry-run=server -f /tmp/dograh-full-render.yaml
task apps:overlays:status project=agentic-ai namespace=dograh app=dograh cluster=bastion
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
Asterisk image=ghcr.io/jtcressy/docker-asterisk:asterisk-22.9.0@sha256:bf7b44aa79128b82d9a21e8f3bbf1227e507599f1de90c57573245636ba1699e
Asterisk image source=https://github.com/jtcressy/containers/tree/main/apps/docker-asterisk
Multus MAC=02:8c:20:0c:1a:01
Multus IP=192.168.20.11
direct-L2 bind=ASTERISK_PJSIP_BINDADDR=192.168.20.11
Stasis app=dograh
websocket client=dograh
extension 7000
```

Static credentials are stored in the `dograh` 1Password item and delivered through ExternalSecrets. Do not print or paste secret values into tickets, docs, manifests, or validation notes.

Required 1Password-backed fields are `POSTGRES_USER`, `POSTGRES_PASS`, `POSTGRES_PASSWORD`, `POSTGRES_SUPER_PASS`, `VALKEY_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `OSS_JWT_SECRET`, `ASTERISK_ARI_PASSWORD`, `UNIFI_TALK_SIP_SERVER`, `UNIFI_TALK_SIP_USERNAME`, `UNIFI_TALK_SIP_PASSWORD`, and `UNIFI_TALK_SIP_EXTENSION`. Shared Cloudflare R2 credentials stay in the `cloudflare-r2-generic` item and are referenced by field name only.

## v2 Media Request Assistant Runtime

Dograh v2 uses Dograh's MCP tool path for active media requests:

```text
Caller on extension 7000
-> Dograh workflow Media Request Assistant
-> Dograh MCP tool media-requests-mcp
-> MetaMCP endpoint media-requests
-> BluePopcorn MCP sidecar upstream jellyseerr-requests
-> Jellyseerr-compatible Overseerr API
```

Runtime inventory:

```text
Active workflow=Media Request Assistant
Workflow id=3
Current published version=7
Private validation extension=7000
Rollback workflow=Cluster Smoke Test
Rollback workflow id=1
Dograh MCP tool=media-requests-mcp
Dograh MCP tool UUID=a1e46e94-f8c0-4f3e-9328-22d079de4760
Dograh credential=metamcp-media-requests-20260530
Dograh credential UUID=548e96c5-259a-496d-813f-669a172d9e49
```

MetaMCP route details:

```text
MetaMCP endpoint name=media-requests
In-cluster URL=http://metamcp.metamcp.svc.cluster.local:12008/metamcp/media-requests/mcp
Tailnet URL=https://metamcp.tailnet-4d89.ts.net/metamcp/media-requests/mcp
MetaMCP upstream=jellyseerr-requests
Upstream transport=STREAMABLE_HTTP
Upstream URL=http://127.0.0.1:9151/mcp
Upstream auth=bearer
BluePopcorn sidecar image=ghcr.io/jtcressy/bluepopcorn-mcp:rolling@sha256:30a64041bfe935dc9c5c625d27b0796a8648f7ef6d8afaad7cdc586c6148d71f
Jellyseerr API URL=http://overseerr.media.svc.cluster.local:5055
```

The BluePopcorn MCP server is a sidecar inside the MetaMCP pod. Port `9151` is for localhost access from MetaMCP; the MetaMCP Service exposes only port `12008`, and the overlay NetworkPolicy allows inbound pod traffic only to the MetaMCP app port.

BluePopcorn image ownership:

```text
Image build repo=https://github.com/jtcressy/containers
Image app path=apps/bluepopcorn-mcp
Published image=ghcr.io/jtcressy/bluepopcorn-mcp
Current tag strategy=rolling plus immutable digest pin in infra
Upstream source=BluePopcorn project, packaged by the containers repo
Rebuild trigger=Renovate or manual source ref bump in jtcressy/containers, then publish GHCR image and update the digest in this infra overlay
```

Live Jellyseerr request semantics observed through the current route:

```text
API base=http://overseerr.media.svc.cluster.local:5055/api/v1
Auth header=X-Api-Key from OVERSEERR_API_KEY
Actor header=X-API-User from DOGRAH_AGENT_USER_ID
Search/detail/request client=BluePopcorn sidecar
Dedicated actor=dograh-agent, Jellyseerr local user id 72
Pending/manual request status observed=2
Available media status may appear on mediaInfo even when the original request has already been cleaned up
Deleted or unavailable validation requests return 404 from GET /api/v1/request/{id}
```

For validation, capture both the Dograh run evidence and external Jellyseerr readback. A clean successful mutation needs a new request id whose `requestedBy.id` matches the dedicated Dograh Agent actor and whose approval state is still pending/manual before cleanup. Do not treat an assistant transcript claim as sufficient evidence.

## v2 Secret Boundaries And Rotation

Keep the three credential scopes separate:

- Jellyseerr API access comes from the existing `overseerr` 1Password item and is rendered into the MetaMCP secret as `OVERSEERR_API_KEY`.
- BluePopcorn sidecar bearer auth comes from the dedicated `BLUEPOPCORN_MCP_API_KEY` field on the `metamcp` 1Password item.
- Dograh gets only the MetaMCP bearer credential in its database credential record; do not put Jellyseerr or BluePopcorn sidecar keys into Dograh.

Rotation paths:

- Jellyseerr API key: rotate the key in Jellyseerr/Overseerr, update the existing `overseerr` 1Password item, let ExternalSecrets reconcile `metamcp-secret`, then roll the MetaMCP pod so the BluePopcorn sidecar reads the new `SEERR_API_KEY`.
- BluePopcorn sidecar bearer key: update `BLUEPOPCORN_MCP_API_KEY` on the `metamcp` 1Password item, let ExternalSecrets reconcile `metamcp-secret`, update the `jellyseerr-requests` upstream bearer configuration in MetaMCP to match, then roll MetaMCP.
- Dograh MetaMCP credential: rotate only the MetaMCP endpoint bearer used by Dograh credential `metamcp-media-requests-20260530`, then update or replace the Dograh credential record and confirm MCP tool `media-requests-mcp` still references the active credential.

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

Asterisk runs as the separate `dograh-asterisk` workload. The image source is `https://github.com/jtcressy/containers/tree/main/apps/docker-asterisk`, and the pinned image is:

```text
ghcr.io/jtcressy/docker-asterisk:asterisk-22.9.0@sha256:bf7b44aa79128b82d9a21e8f3bbf1227e507599f1de90c57573245636ba1699e
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

Dograh `1.29.0` builds the ARI event websocket URL with the ARI password in the `api_key` query parameter. Keep `ASTERISK_ARI_PASSWORD` URL-safe until Dograh URL-encodes that value; validation on 2026-05-17 required rotating this field to a letters/digits-only value after Asterisk rejected the first connection with HTTP 401.

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

The v1 no-tool workflow is now the rollback smoke workflow, not the active v2 Media Request Assistant. It should answer the inbound call, converse briefly, and prove that Dograh receives caller audio and returns model audio through Asterisk.

Configure the workflow inside Dograh after the app is healthy:

```text
Workflow purpose=real inbound call infrastructure validation
Workflow name=Cluster Smoke Test
Workflow id=1
Tools=none
Assigned telephony provider=Asterisk ARI
Assigned phone number or extension=7000 when rolled back from v2 validation
Expected behavior=brief spoken response without external tool calls
```

Do not add external media tooling, request tooling, or application-specific smoke cases to this smoke workflow. Keep it available as the immediate rollback target for extension `7000`.

## Health And Logs

Overlay and ArgoCD checks:

```bash
task apps:overlays:render project=agentic-ai namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=agentic-ai namespace=dograh app=dograh cluster=bastion
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

If CNPG restore is unavailable and Dograh database state must be recreated, rebuild only the app-local Dograh objects from the current runbook and planning facts:

1. Confirm Dograh API/UI, Asterisk, MetaMCP, and the BluePopcorn sidecar are healthy before recreating app state.
2. Recreate the Dograh MCP tool `media-requests-mcp` pointing at the MetaMCP `media-requests` endpoint.
3. Recreate the Dograh credential `metamcp-media-requests-20260530` with only the MetaMCP bearer token.
4. Recreate or import the `Media Request Assistant` workflow and publish the expected version, currently workflow id `3` version `7`.
5. Attach MCP tool `media-requests-mcp` to the workflow.
6. Assign extension `7000` to `Media Request Assistant` for private validation.
7. Keep `Cluster Smoke Test` workflow id `1` available as the rollback assignment for extension `7000`.
8. Run the v2 validation checklist below and record evidence before treating the recreate as complete.

## Rollback And Cutover

Before cutover:

```bash
task apps:overlays:render project=agentic-ai namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=agentic-ai namespace=dograh app=dograh cluster=bastion
kubectl -n dograh rollout status deploy/dograh-api deploy/dograh-ui deploy/dograh-asterisk
kubectl -n dograh exec deploy/dograh-asterisk -- asterisk -rx 'pjsip show registrations'
```

Cutover is only complete after `Media Request Assistant` workflow id `3` is assigned to extension `7000` and a real inbound call proves the Dograh MCP tool to Jellyseerr path. Keep the previous UniFi/OpenClaw Voice path available until the Dograh call path is proven.

Rollback options:

- Revert the Dograh GitOps commit if the overlay change is the cause.
- Re-sync ArgoCD after revert and verify app health with the task status wrapper.
- Reassign extension `7000` from `Media Request Assistant` workflow id `3` back to `Cluster Smoke Test` workflow id `1` if the v2 tool path fails but the call infrastructure is healthy.
- Return UniFi Talk routing to the previous known-good target if Asterisk registration or two-way audio fails.
- Preserve CNPG and MinIO data while investigating unless a deliberate restore plan has been approved.

Do not move the overlay to `disabled/` manually. Use the repo overlay tasks for app lifecycle operations.

## Real Inbound Call Validation

This section is the operator checklist for Task 3 live validation. Do not mark it complete from local render checks alone.

Completed validation, 2026-05-17T04:17:17Z:

These entries reflect the AppProject layout at validation time; current operator commands above use `project=agentic-ai`.

- PASS: `task apps:overlays:render project=home namespace=dograh app=dograh cluster=bastion` rendered the fully wired overlay locally.
- PASS: forbidden-pattern scans found no app-template usage, host networking, Funnel, VolSync/restic MinIO backup resources, `mc mirror --remove`, or Compose-local host assumptions in the Dograh overlay.
- PASS: `argocd login argocd.tailnet-4d89.ts.net --sso` completed successfully for the CLI.
- PASS: `argocd app get argocd/metamcp-bastion --grpc-web` confirmed the logged-in CLI can inspect an existing app.
- PASS: `task apps:overlays:status project=home namespace=dograh app=dograh cluster=bastion` reported `argocd/dograh-bastion` synced to HEAD commit `d9a6783` and `Healthy`.
- PASS: `kubectl -n dograh get pods,ingress,cluster,tenant,cronjob` showed Dograh API/UI/Asterisk/Valkey/CNPG/MinIO running, CNPG healthy, MinIO Tenant initialized/green, and MinIO R2 backup CronJob present.
- PASS: Asterisk `pjsip show registrations` reported `unifi-talk-registration/sip:192.168.20.1:5060` as `Registered`.
- PASS: Asterisk `http show status` showed ARI enabled on port `8088`.
- PASS: Asterisk `ari show apps` listed `dograh`.
- PASS: Dograh API health through the tailnet returned status `ok`, version `1.29.0`, and `auth_provider: local`.
- PASS: Dograh telephony config `Dograh Asterisk` used provider `ari`; extension `7000` was active and mapped to workflow `1`, `Cluster Smoke Test`.
- PASS: Real inbound call from UniFi Talk caller `0003` to extension `7000` created Dograh workflow run `1`, answered in Asterisk Stasis, created and bridged the external media websocket channel, connected Gemini Live, completed normally with cause `16 (Normal Clearing)`, uploaded `recordings/1.wav`, and uploaded `transcripts/1.txt`.
- NOTE: Dograh logged a non-blocking warning while parsing the initial Asterisk `MEDIA_START` frame as JSON. The pipeline continued, Gemini Live connected, artifacts were written, and teardown was normal.

Pre-call checks:

```bash
task apps:overlays:render project=agentic-ai namespace=dograh app=dograh cluster=bastion
task apps:overlays:status project=agentic-ai namespace=dograh app=dograh cluster=bastion
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
3. Confirm Media Request Assistant workflow id 3, published version 7, is assigned to extension 7000.
4. Place a real inbound UniFi Talk call.
5. Confirm Dograh hears caller audio.
6. Confirm the caller hears Dograh's model response.
7. Confirm the transcript shows the media request intent and tool result without secret values.
8. Capture the Dograh run id or transcript id.
9. Capture Jellyseerr before/after evidence proving the requested item was created or changed.
10. Clean up the test request in Jellyseerr when the request was validation-only.
11. Record pass/fail evidence without secret values.
```
