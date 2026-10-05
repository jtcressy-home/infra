# Incident adapter

Review-only implementation for OPS-5. One Python process receives Alertmanager v4
webhooks, persists incident state in SQLite and delivers Discord text and direct
MCP Events. No deployment overlay, credentials, subscription or live receiver
configuration is included. The existing receiver stays `staging-no-delivery`.

## Run and test

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
# From the repository root with that environment on PATH:
task alerting:adapter-test
# Build from this directory:
docker build -t incident-adapter:review .
```

Tests use temporary databases, fake clocks/transports, synthetic signing keys and
a loopback HTTP server. They never contact Discord, a callback, Jira or Bastion.
The container runs as UID/GID 10001. Mount an approved configuration file and set
`ADAPTER_CONFIG_FILE` to its path. `config.example.json` has file references only;
its example issuer/resource/Jira URLs and telemetry query must be replaced with
reviewed values before starting a real instance. Secret files must be readable by
UID 10001. The database directory must be writable and private to that identity.

## Interfaces and state

- `POST /hooks/alertmanager` requires its separate bearer token. Valid v4 input
  commits atomically before 200. Storage/capacity failures return 503. Input is
  limited to 1 MiB. Each alert's status matters; truncated input is incomplete.
- `POST /mcp` implements JSON-RPC protocol 2026-07-28, discovery, event methods and
  incident tools. OAuth JWTs require a configured issuer, resource audience,
  expiry and approved subject. Only RS256/ES256 are accepted. The grants file is
  reloaded for authorization and callback delivery; token scopes are intersected
  with configured grants. Read and ACK scopes are separate.
- `/healthz` tests database connectivity. `/readyz` requires recent healthy source
  observations. Neither proves delivery. Private `/metrics` exposes aggregate
  source health, delivery states, expired deliveries, worker errors and database
  bytes. Restrict operational endpoints at the service/network boundary.

SQLite uses WAL, synchronous FULL and explicit transactions. Incident IDs derive
from source, fingerprint and firing onset. Normalized labels and source/observed
times are retained. Each alert episode is one incident. A duplicate cannot reset
the clock, and an old resolution cannot close a later episode. State transitions,
revisions, journal events and destination outbox entries commit together.

Initial delivery is prompt. Ordinary reminders start one hour after validated
onset and repeat hourly. Late cutover gets one initial summary; downtime reminders
coalesce. ACK or recovery cancels queued ordinary messages in both channels.
Worsening remains visible after ACK. A request already in flight can still arrive;
its receipt is retained even when a concurrent refresh replaces its queue lease.
External delivery is at least once under ambiguous responses, not exactly once.

Discord and dot have separate workers and retry state. There are at most ten
attempts, exponential delays capped at 15 minutes plus jitter; a provider's
Retry-After may require a longer wait. Discord requires a message ID receipt.
Callbacks stop on 410, quarantine 413 and retain exhausted attempts for inspection.
Missing Discord configuration becomes a visible blocked delivery.

The journal and delivery records retain seven days, including failed deliveries.
Expiration increments a counter, so failures are not silently treated as success.
Recovered episode tombstones retain 30 days; replaying source input older than
that window can create an episode again. Idempotent write results retain seven
days. Limits are 10,000 incidents, 50,000 journal events, 200,000 destination rows,
100,000 request results and 1,000 subscriptions. Capacity failures reject the whole
transaction. These row limits do not substitute for volume capacity monitoring.

## MCP Events and ACK

`monitoring.incident_changed` requires exactly `{"cluster":"bastion"}`. Its
allowlisted payload contains incident ID, revision, kind, severity, summary,
observation time and an optional Jira URL. Raw annotations and logs are excluded.
Subscribe accepts name, arguments, delivery mode/url/secret, ttlMs and cursor;
it returns id, refreshBefore, cursor and truncated. Identity is deterministic for
the authenticated principal, event, canonical arguments and callback URL.

Callbacks must be public HTTPS on port 443. Every connection resolves and checks
all addresses, pins a public address and verifies TLS for the original hostname.
Private/mixed DNS answers and redirects are rejected. A ten-second total request
deadline includes DNS, connect, TLS handshake, headers and response body. Socket
shutdown interrupts slow-drip responses so the next subscription can proceed.
DNS waits are bounded; at most four resolver threads can remain outstanding if
the system resolver stalls. Resolver saturation fails delivery for retry rather
than blocking the worker indefinitely. Verification uses a signed,
single-use challenge and constant-time echo comparison. The same verified key and
callback may use a five-minute verification cache. Leases last at most 24 hours.
A caller must refresh before expiry. Revoked principals stop delivering.

Secrets are Fernet-encrypted in SQLite using the approved key file. Preserve this
key with the database; startup rejects existing ciphertext under a different key.
Webhook signing uses Standard Webhooks over exact serialized bytes, stable event
IDs and a fresh timestamp per attempt. Rotation dual-signs for five minutes.
Delivery envelopes carry a contiguous accepted cursor, so an out-of-order receipt
cannot skip an earlier pending event. Expired replay history reports truncated;
the client must reconcile `list_incidents`. Stale ordinary reminders are cancelled
against current state before sending. A reminder superseded by a newer slot is
cancelled even after cursor rewind, subscription renewal, restart or a new
subscription; retained history cannot restore a burst of old reminders.

Read tools are `list_incidents` and `read_incident`. `record_event_seen` records
agent handling separately and never ACKs. All writes require request IDs;
incident commands require the expected revision. `ack_incident`, `snooze_incident`
and `rearm_incident` require `monitoring:ack`. Snooze lasts at most 24 hours.

Before an agent ACK, TARS must create or locate the correlated OPS ticket using
its existing Jira connector and read back the ticket and diagnostic comment.
Supply ticket key, exact configured-origin URL, incident ID, verification time
within 15 minutes and comment ID. The adapter records the authenticated caller's
assertion, not independent Jira verification. A failed or uncertain Jira read
leaves reminders active. An authorized human may ACK without ticket evidence.
Jira status changes and callback receipts never ACK an incident.

## Recovery and activation prerequisites

Every minute the source worker reads Alertmanager with active, silenced, inhibited
and unprocessed alerts enabled. It checks fresh successful VMAlert rule evaluations
and the explicitly configured required-telemetry query. The query must return
exactly one recent vector sample equal to 1 when all required collection signals
are healthy. A generic single-target `up` query is insufficient. Validate the
query and API response shapes against the intended instance before activation.

Explicit resolved input needs healthy sources, or two healthy absence observations
at least 30 seconds apart establish recovery. Missing or malformed telemetry makes
state unknown, and a synthetic monitoring-health incident reports observer failure.
No Alertmanager silence writes are implemented.

Activation is a separate reviewed change and must provide:

1. An immutable published image, one replica with Recreate rollout, a dedicated
   local-backed writable volume and node placement. Start sizing at 2 GiB and
   measure load. Add filesystem usage alerts at 70%/85%, including WAL growth,
   before accepting capacity. Do not use the shared database or zfs-nvme volume.
2. An approved database/key backup target and SQLite-consistent backup/restore
   procedure, tested to preserve incident IDs, ACKs and delivery identities. Never
   copy only the SQLite main file while WAL writes are active. Node loss remains
   a gap. SIGTERM/crash recovery relies on SQLite transaction durability and
   30-second queue leases; coordinate shutdown before backup.
3. Existing issuer/JWKS/resource configuration, approved principal grants,
   ingress or private tunnel that passes direct event discovery, network policy,
   and mounted secret references. Confirm the platform can reach callbacks and
   the service can reach its source APIs. Do not assume MetaMCP forwards events.
4. The approved Discord destination, encryption key and Alertmanager source token.
   Replace the staged receiver only after adapter readiness, with send_resolved
   true, max_alerts 0 and a ten-second timeout. No secrets belong in Git.
5. Separate approval for a real dot subscription and synthetic messages. Prove
   evaluator-to-receiver, Discord receipt, dot wake plus record_event_seen,
   ticket-first ACK, cancellation in both channels, restart/replay and recovery.
   A callback 2xx alone is not proof that dot handled an event.

Kuma, Grafana repair, database signal coverage expansion and whole-Bastion/home
loss detection remain outside this implementation. Rollback stops outbound
workers/subscriptions and retains the database/key. Never delete state as rollback.
