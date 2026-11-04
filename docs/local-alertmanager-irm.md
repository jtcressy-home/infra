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

The integration URL contains a token and is not stored in git. External Secrets
reads it from the existing `onepassword` ClusterSecretStore (vault
`jtcressy-net-infra`) and writes Secret
`monitoring/grafana-irm-alertmanager-bastion`.

| 1Password | Value |
| --- | --- |
| Vault | `jtcressy-net-infra` |
| Item title | `grafana-irm-alertmanager-bastion` |
| Field label | `url` |

The field value is the inbound URL of integration C254NSW1QG433, copied
exactly, including a trailing slash. Joel creates the item. The operator mounts
the key at `/etc/vm/secrets/grafana-irm-alertmanager-bastion/url`. Both the
page receiver and the Watchdog receiver read that file. Each webhook sends at
most 100 alerts, which is the cap Grafana documents for this integration.
Leave the IRM grouping template at `payload.groupKey` so resolution still
matches these groups. A missing item leaves
the ExternalSecret not Ready, the Secret absent, and the Alertmanager pod
unable to start. Do not print the URL in logs, CI, PRs, or this document.

Watchdog is the heartbeat. A later change turns it into an IRM dead-man's
switch (page only after it stops arriving, 3 minute timeout, configured
outside this repository). This change only makes sure Watchdog is delivered.

## Routing

Alerts are delivered by default. `irm_notify` is still set on the three
`CNPGPrimaryUnavailable` rules, but it is not a route gate.

| Timers | Value |
| --- | --- |
| `group_by` | `alertname`, `namespace`, `cluster` |
| `group_wait` | 30s |
| `group_interval` | 5m |
| `repeat_interval` | 4h |
| Watchdog repeat | 1m, `group_wait` 0s, resolved notifications off |

Grouping is what keeps the alerts firing today from opening one IRM incident
per series. A critical alert inhibits the warning with the same `alertname`
and `namespace`. `InfoInhibitor` goes to the null receiver.

Known-broken noise is routed to the null receiver, with a TODO in
`vmalertmanager.yaml` that points at the monitoring gap inventory (batch 0,
2026-11-03). The rules stay in place.

| Noise | Why it matches |
| --- | --- |
| lidarr CrashLoop | `namespace=media` and `pod=~lidarr-.+` or `deployment=lidarr` |
| recyclarr | `namespace=media` and `job_name` or `pod` starting with `recyclarr` |
| spegel | `namespace=kube-system` and `daemonset=spegel`, `pod=~spegel-.+`, or TargetDown for service/job `spegel` |
| Retired-node TargetDown | kubelet only. The stock rule aggregates by job, namespace, and service and has no node label, so `service=kps-kubelet` (job `kubelet` or `kps-kubelet`) is suppressed until `talos-master-1`, `talos-master-2`, `talos-worker-gpu-1`, and the stale 100.x master-0 endpoint are removed |

Other firing alerts are still delivered, one group per alert name and
namespace. That includes VolSync out of sync, `dograh-minio-r2-backup` job
failures, and `KubeNodeNotReady` for nodes that are still NotReady. Those are
not in the inventory's do-not-page list.

The CNPG rules page when a database has no pod that is scraped, has a healthy
collector, and is primary for five minutes. They keep a stable database
identity (no pod name or IP). The alerts VMSingle minimum staleness is five
minutes, so a missing series is also bounded by that lookback before `for: 5m`.

## How to verify

CI renders this overlay with `task apps:overlays:render`, checks the image
digests and the ExternalSecret item name, runs `amtool check-config` on
Alertmanager v0.29.0, and checks the routes above with `amtool config routes`
in a container that has no network. Promtool runs the offline CNPG scenarios.
None of that sends a live alert or reads the 1Password value.

Before relying on pages, after the item exists and a sync is approved:

1. ExternalSecret `grafana-irm-alertmanager-bastion` is Ready. Confirm the
   Secret has a key named `url`. Do not print the value.
2. Pods for `VMAlertmanager/local` are Ready and VMAlert's notifier is
   `http://vmalertmanager-local.monitoring.svc:9093`.
3. Integration C254NSW1QG433 shows a firing Watchdog group within about a
   minute, and it keeps updating. It should not be treated as a page until
   the dead-man's switch exists.
4. A lidarr, recyclarr, spegel, or kubelet TargetDown alert does not open an
   IRM incident. A different firing alert, such as VolSync, does, as one group
   per alert name and namespace.
5. Resolving an alert resolves the matching IRM group (`send_resolved` is on
   for the page receiver, off for Watchdog).

`amtool` route tests do not simulate inhibition. Inhibition is asserted from
the rendered config: critical suppresses warning when `alertname` and
`namespace` match. CI does not run the operator, admit the CRD, or resolve
the Secret.

## Rollback

Revert this change and sync the `victoria-metrics` application. That removes
`VMAlertmanager/local` and the ExternalSecret, and points VMAlert back at
`alertmanager.monitoring.svc` and `alertmanager-local-0..2`, which do not
exist. Delivery stops again. The Secret's deletion policy is Retain, so
delete `monitoring/grafana-irm-alertmanager-bastion` by hand if the credential
should go too. Leave the 1Password item unless the integration itself is
retired. Do not print the URL while cleaning up.

References:

- [VMAlertmanager](https://docs.victoriametrics.com/operator/resources/vmalertmanager/)
- [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Grafana Alertmanager integration](https://grafana.com/docs/grafana-cloud/alerting-and-irm/irm/integrations/alert-sources/alertmanager/)
