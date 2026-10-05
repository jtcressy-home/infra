# Bastion alerting restoration

This change prepares Alertmanager intake and an incident adapter for review.
The adapter source is implemented and tested but has no deployment overlay. The receiver deliberately discards notifications while
Alertmanager retains active alerts for inspection. Successful VMAlert requests
alone must not be reported as working alert delivery. Do not merge or deploy
until the phase-specific approval below is recorded.

## Phase 1: receiver intake

Reuse kube-prometheus-stack 82.10.5 and its existing Prometheus operator. Enable
Alertmanager v0.31.1, one replica, in kube-system. VMAlert uses one notifier,
`http://kps-alertmanager.kube-system.svc:9093`, replacing the four obsolete
monitoring-namespace destinations. Rule evaluation and telemetry storage stay
unchanged. No new namespace, external ingress, credential or subscription is added.

The rendered receiver is `staging-no-delivery`. Its route has no child receivers
or inhibition rules. Nil AlertmanagerConfig selectors prevent the operator from
importing other receivers. No Discord webhook or adapter endpoint is configured.
Group timing is 10 seconds initially and one minute between changes; the one-hour
repeat interval is only a transport setting. It does not implement the shared
incident reminder clock.

Alertmanager requests a dedicated 1Gi ReadWriteOnce claim from the existing `local`
StorageClass. That class uses the local-hostpath CSI provisioner, not zfs-nvme.
The operator creates the StatefulSet and claim after reconciliation. This stores
Alertmanager state only. Adapter incident, ACK and outbox state must have a
separate volume. Local storage is node-bound, not replicated, and does not survive
loss of its backing node. Verify node placement, capacity and recovery before use.

The chart adds six objects: Alertmanager, ClusterIP Service, ServiceAccount,
configuration Secret containing no credentials, ServiceMonitor and dashboard
ConfigMap. All 95 previously rendered objects are unchanged. The VictoriaMetrics
overlay changes only VMAlert's notifier list. The existing rules are preserved;
this phase does not claim complete database, storage, backup or WAL signal coverage.

## Phase 2: direct incident adapter implementation

The [adapter source and operations guide](../services/incident-adapter/README.md) implement
an authenticated MCP endpoint and a private Alertmanager webhook endpoint. It
owns both Discord #alerts text and dot events, 24 hours a day. There are no calls,
paging escalation, Gmail relay or Discord bot. Kuma and Grafana repair are outside
this change. A Bastion-hosted adapter cannot report total Bastion or home loss.

Use SQLite transactions, WAL and synchronous FULL on a dedicated local-backed
2Gi claim initially, one process/replica and a Recreate deployment strategy.
Bound the seven-day journal and outbox, alert at 70% and 85% usage, and measure
retention under representative load before accepting the size. Do not use shared
PostgreSQL, zfs-nvme, the metrics queue PVC or ephemeral alert storage. Require a
separately approved backup target and a restore test that preserves incident IDs,
ACK state and delivery identities. Protect callback signing secrets at rest using
an approved secret-management arrangement. Node loss remains an explicit gap.

### Input and recovery

After adapter readiness and authorization are approved, replace the staging
receiver with the standard Alertmanager v4 webhook. Use `send_resolved: true`,
`max_alerts: 0` and a 10-second timeout. Store the whole accepted state transition
before returning 2xx; return 503 on persistence failure. Impose request size limits,
authenticate the source and reject malformed input without partial writes.

Use source, fingerprint, validated startsAt and normalized labels to identify a
firing episode. Assign a durable internal incident ID. Never use groupKey alone.
Handle each member's firing/resolved status independently. Duplicate updates do
not reset onset; an old resolved episode cannot close a later one. A truncated
payload or a missing group member cannot prove recovery.

Reconcile every minute against `/api/v2/alerts` with active, silenced, inhibited
and unprocessed all enabled. Missing alerts while evaluation or telemetry is
unhealthy mean unknown, not recovered. Require explicit resolution with healthy
evaluation or repeated healthy source observations for every member. Do not turn
ACK into an Alertmanager silence or infer recovery from a Jira status change.

### State and delivery

Persist incidents, members, revisions, ACK assertions, subscriptions, event journal
and independent Discord/dot outbox entries. Commit state and outbox in one
transaction. Unique incident/revision/kind/destination keys prevent duplicate
scheduling. Lease pending deliveries and check current state immediately before
send. Provider receipt and agent handling are different records.

Send one initial message promptly. First ordinary reminder is due one hour after
validated onset, then hourly until ACK or recovery. Preserve source onset and
first-observed timestamps. On late cutover send one overdue summary, then the next
hourly slot. After downtime coalesce overdue reminders instead of replaying a
burst. ACK/recovery cancels pending ordinary reminders in both channels. In-flight
messages can still arrive. A worsening risk emits a new visible revision even
while acknowledged. Snooze has an explicit expiry; rearm resumes the same clock.

Use bounded retries per destination, ten attempts with exponential backoff capped
at 15 minutes, jitter and Retry-After. Preserve ambiguous/exhausted deliveries for
inspection. A failed channel must not block the other. Do not promise exactly-once
external delivery when provider responses are ambiguous.

### MCP Events and tools

Follow the [MCP Events contract](https://developers.openai.com/plugins/build/mcp-events)
and test the wire protocol before choosing an SDK. Use authenticated MCP protocol
2026-07-28 with `server/discover`, tools/events capabilities, `events/list`,
`events/subscribe` and `events/unsubscribe`. An ordinary tools-only connection is
insufficient. Validate issuer, audience and separate read/ACK scopes through the
existing identity provider; no authentication setup is included here.

Define `monitoring.incident_changed`, webhook-only, with required `cluster` filter
restricted to `bastion` and no extra arguments. Payload fields are incident_id,
revision, kind, severity, summary, observed_at and optional jira_url. Kinds are
opened, reminder, worsened, recovered and monitoring_unknown. Severities are warning
and critical. Publish sanitized facts, never raw logs or agent instructions.

Subscriptions are principal-scoped and durable, with canonical arguments, verified
HTTPS callbacks, protected signing secrets and a maximum 24-hour lease. Enforce
callback destination safety on every connection, forbid redirects and validate
signed challenges before activation. Support renewal, revocation, unsubscribe and
key rotation. Use Standard Webhooks over exact serialized bytes. Preserve event
IDs across retries; stop on 410 and quarantine 413. Retain a seven-day replay
journal and only advance contiguous acknowledged delivery cursors; report truncated
history and reconcile current incidents. Callback 2xx is receipt, not agent ACK.

Tools are list_incidents, read_incident, record_event_seen, ack_incident,
snooze_incident and rearm_incident. Writes require an idempotency request ID and
expected revision; derive caller identity from authentication. TARS reads current
state and records event handling separately. Before agent ACK, TARS uses the
existing Jira connector to create or locate the OPS incident and reads it back,
verifying correlation ID, ticket URL and diagnostic evidence comment. ACK records
ticket key, URL, verification time and evidence comment ID as the authenticated
caller's assertion, not as independent server-side Jira verification. Missing or
uncertain evidence leaves reminders active. No new Jira credentials are needed.
Human ACK in dot uses the same state. A Jira status change alone has no effect.

## Validation and activation gates

Local phase-one checks:

```sh
# Requires task, kustomize 5.7.1, Helm 3, Python with PyYAML and amtool 0.31.1.
task alerting:validate outputDir=/tmp/alerting-validation
task apps:overlays:diff-pr-test
git diff --check
# With the pinned adapter requirements installed:
task alerting:adapter-test
```

Approve rollout in these steps:

1. Review the exact commit and passing checks. Verify the current operator/CRDs,
   `local` StorageClass, capacity and Application sync policies using read-only
   checks. Preview live differences. A full application sync could reconcile
   unrelated drift even when the Git diff preserves existing objects.
2. Approve only the six receiver resources and operator-generated StatefulSet/PVC.
   Verify ready endpoints and the loaded staging configuration before approving
   the VMAlert notifier change. A Service alone is not readiness. Observe real
   firing state reaching Alertmanager without sending synthetic alerts.
3. Review the included adapter implementation and run its synthetic fixtures for duplicate, late, mixed and
   truncated webhooks; commit failure and restarts; hourly timing and late cutover;
   ACK/send races and failed ticket verification; recovery while acknowledged or
   silenced; missing telemetry; channel isolation; callback/signature failures;
   SSRF/redirect rejection; replay gaps, expiry, rotation and revoked access.
4. Separately approve adapter storage/backup, source authentication, plugin access,
   the existing Discord destination, dot subscription and synthetic messages.
   Prove evaluator-to-receiver, Discord receipt, dot wake plus record_event_seen,
   ticket-first ACK, both-channel cancellation and recovery. Only then activate
   real delivery and claim notification coverage. Audit database signal gaps next.

Rollback before delivery activation leaves the receiver inert. Roll back only the
VMAlert notifier change if needed; its old destinations were absent, so that is
not restored delivery. Preserve the new receiver PVC until separately approved
for removal. Later adapter rollback pauses outbound workers/subscriptions while
retaining its journal and ACK state. Do not delete shared resources or silently
restore obsolete receivers. No merge, deploy, credential creation, subscription
or test message is authorized by this document.
