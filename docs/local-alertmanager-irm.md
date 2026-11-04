# Local Alertmanager to Grafana Cloud IRM

Bastion VMAlert evaluates the in-cluster rules and sends them to one
Alertmanager run by the existing VictoriaMetrics operator. That Alertmanager
delivers to Grafana IRM integration **C254NSW1QG433** ("Home infrastructure
Alertmanager"). There is no ingress, public service, or payload transformer.

VMAlert's notifier is `http://vmalertmanager-local.monitoring.svc:9093`, the
Service the operator creates for `VMAlertmanager/local`. The previous
notifiers (`alertmanager.monitoring.svc` and `alertmanager-local-0..2`) do not
resolve, which is why firing alerts were dropped.

The Alertmanager image is `prom/alertmanager:v0.29.0` pinned by digest, and the
file-watching config reloader is
`quay.io/prometheus-operator/prometheus-config-reloader:v0.82.1` pinned by
digest. `useVMConfigReloader: false` keeps the reloader on file watches, so the
pod uses the default service account with token automount disabled and the
operator does not add a config-watcher Role. Operator v0.66.1 joins
`image.repository` and `image.tag` with a colon, so the digest lives in the
tag (`v0.29.0@sha256:…`). That string is not valid semver, so the operator
skips its own version check; `extraArgs.enable-feature=utf8-strict-mode` keeps
the flag that v0.29.0 would otherwise get. The reloader field on this operator
is `configReloaderImageTag`, and it is the full image reference.

This is a single replica with ephemeral storage. Replacing the pod drops local
silences and the notification log, so a still-firing alert can be sent again.
IRM keeps the incident identity from the alert group key.

## 1Password item

The integration URL contains a token and is not stored in git. The item has
to exist before this change is merged. If it does not, the ExternalSecret
never becomes Ready, the Secret is absent, and the Alertmanager pod stays
Pending.

| 1Password | Value |
| --- | --- |
| Vault | `jtcressy-net-infra` (ClusterSecretStore `onepassword`) |
| Item title | `grafana-irm-alertmanager-bastion` |
| Field label | `url` |

The field value is the inbound URL of integration C254NSW1QG433, copied
exactly, including a trailing slash. ExternalSecret
`monitoring/grafana-irm-alertmanager-bastion` templates two Secret keys from
that field:

| Secret key | Value |
| --- | --- |
| `url` | the 1Password field, unchanged |
| `heartbeat_url` | that URL plus `heartbeat/` |

The page receiver reads `url`. Watchdog reads `heartbeat_url`, which is
Grafana's Alertmanager heartbeat endpoint and is not on the escalation chain.
Each webhook sends at most 100 alerts. Leave the IRM grouping template at
`payload.groupKey`. Do not print the URL in logs, CI, PRs, or this document.

`creationPolicy: Owner` sets an ownerReference on the Secret. Deleting the
ExternalSecret deletes the Secret with it. `deletionPolicy: Retain` only
keeps the Secret when the 1Password item itself disappears.

## Routing

The root receiver is `null`. Only alerts with `irm_notify="true"` go to
`grafana-irm`. Today that label is set on the three `CNPGPrimaryUnavailable`
rules and nowhere else, so the rest of the firing set does not page.

| Timers | Value |
| --- | --- |
| `group_by` | `alertname`, `namespace`, `cluster` |
| `group_wait` | 30s |
| `group_interval` | 5m |
| `repeat_interval` | 4h |
| Watchdog | `group_interval` 1m, `repeat_interval` 50s, `group_wait` 0s, `send_resolved` false |

Watchdog is posted to the heartbeat URL about every 50 seconds so it stays
inside the integration's 600 second heartbeat timeout. It does not page.
Resolved notifications are off for that receiver.

When `VolSyncVolumeOutOfSync` is opted in later, give that alert its own route
grouped by `obj_namespace` and `obj_name`. The default `namespace` group would
collapse every ReplicationSource into one incident.

A critical alert inhibits the warning with the same `alertname` and
`namespace`. `InfoInhibitor` inhibits `severity="info"` in the same namespace,
and the `InfoInhibitor` alert itself goes to the null receiver.

Known-broken noise is also routed to null, above the `irm_notify` route, so a
later opt-in still cannot page it. The rules stay. The TODO in
`vmalertmanager.yaml` points at the monitoring gap inventory (batch 0,
2026-11-03).

| Noise | Why it matches |
| --- | --- |
| lidarr | `namespace=media` and `deployment=lidarr`, or a pod named `lidarr-*` or `volsync-src-lidarr-rsrc-*`, or `obj_name=lidarr-rsrc` |
| recyclarr | `namespace=media` and `job_name` or pod starting with `recyclarr`, or `volsync-src-recyclarr-rsrc-*`, or `obj_name=recyclarr-rsrc` |
| spegel | `namespace=kube-system` and `daemonset=spegel`, `pod=~spegel-.+`, or TargetDown for service/job `spegel` |
| Retired kubelet endpoints | `TargetDown` with `namespace=kube-system` and `service=kube-prometheus-stack-kubelet` only. That is the legacy orphaned Endpoints object. The live kubelet Service is not matched |

The CNPG rules page when a database has no pod that is scraped, has a healthy
collector, and is primary for five minutes. They keep a stable database
identity (no pod name or IP). The alerts VMSingle minimum staleness is five
minutes, so a missing series is also bounded by that lookback before `for: 5m`.

## How to verify

CI renders this overlay with `task apps:overlays:render`, checks the image
digests, the 1Password item name, and the `heartbeat_url` template, runs
`amtool check-config` on Alertmanager v0.29.0, and checks the routes above
with `amtool config routes` in a container that has no network. An alert
without `irm_notify` must resolve to `null`. One with `irm_notify="true"`
must resolve to `grafana-irm`, unless it is Watchdog or known noise. Promtool
runs the offline CNPG scenarios. None of that sends a live alert or reads the
1Password value.

Before relying on pages, after the item exists and a sync is approved:

1. ExternalSecret `grafana-irm-alertmanager-bastion` is Ready. Confirm the
   Secret has keys `url` and `heartbeat_url`. Do not print the values.
2. Pods for `VMAlertmanager/local` are Ready and VMAlert's notifier is
   `http://vmalertmanager-local.monitoring.svc:9093`.
3. Integration C254NSW1QG433 shows a fresh heartbeat and does not escalate
   Watchdog. A missing heartbeat is the later dead-man's switch, not this page.
4. An alert without `irm_notify` does not open an IRM incident. A
   `CNPGPrimaryUnavailable` alert does.
5. Resolving a paged alert resolves the matching IRM group. Watchdog does not
   send resolved.

`amtool` route tests do not simulate inhibition. Inhibition is asserted from
the rendered config. CI does not run the operator, admit the CRD, or resolve
the Secret.

## Rollback

Two ways to stop pages without reverting the branch:

1. Turn on maintenance mode for IRM integration C254NSW1QG433.
2. In `vmalertmanager.yaml`, set the `irm_notify="true"` route receiver to
   `"null"`. The root receiver is already `"null"`, so that one line is the
   paging gate.

Reverting the change and syncing `victoria-metrics` also stops delivery. It
removes `VMAlertmanager/local` and the ExternalSecret, and points VMAlert back
at `alertmanager.monitoring.svc` and `alertmanager-local-0..2`, which do not
exist. `creationPolicy: Owner` deletes Secret
`monitoring/grafana-irm-alertmanager-bastion` together with the ExternalSecret.
Leave the 1Password item unless the integration itself is retired. Do not
print the URL while cleaning up.

References:

- [VMAlertmanager](https://docs.victoriametrics.com/operator/resources/vmalertmanager/)
- [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Grafana Alertmanager integration](https://grafana.com/docs/grafana-cloud/alerting-and-irm/irm/integrations/alert-sources/alertmanager/)
