# Local Alertmanager to Grafana Cloud IRM

The VictoriaMetrics overlay creates one standard Prometheus Alertmanager through
the existing VM operator. VMAlert sends to the operator's internal service,
`http://vmalertmanager-local.monitoring.svc:9093`. There is no ingress, public
service, additional monitoring stack, or payload transformer. The file-watching
reloader uses the existing default service account with token automount disabled;
the operator does not add a config-watcher Role or RoleBinding.

## Secret prerequisite

Before any separately approved rollout, provide Kubernetes Secret
`monitoring/grafana-irm-endpoints` through the approved secret store:

| Key | Value source |
| --- | --- |
| `integration_url` | Sensitive Terraform output `irm_alertmanager_integration_url` from the separate IRM repository. Preserve the URL exactly, including its trailing slash. |
| `heartbeat_url` | Native heartbeat endpoint configured separately in IRM for that integration. Provider 4.49 has no heartbeat resource/output. |

This PR only references the Secret. It does not create credentials, an
ExternalSecret with an invented remote item, or endpoint values. The operator
mounts these keys under `/etc/vm/secrets/grafana-irm-endpoints/`.
Both keys are required; a missing Secret prevents the Alertmanager pod starting.
Do not print endpoint values in logs, CI, PRs, or this document.

## Routing and grouping

The initial route sends only alerts with `irm_notify="true"` to IRM. Three
`CNPGPrimaryUnavailable` rules opt in database-primary health for
`dograh/dograh-db`, `kagent/kagent-db`, and `teslamate/teslamate-db`.
Each requires five minutes without a pod that is simultaneously scraped
successfully, has a healthy collector, and reports primary role. The signals
join on k8s_cluster, namespace, job, and pod, then collapse to stable database
identity. Explicit output labels survive complete series loss and exclude pod
names and IPs, so primary replacement does not change the database incident.

Missing-series detection also depends on datasource staleness/lookback before
the five-minute pending period; the alerts VMSingle sets a five-minute minimum
staleness interval. These rules detect loss of observable primary health, which
can reflect a database failure or loss of its monitoring path.

All other ordinary alerts go to the null receiver. Broad Kubernetes and backup
backlogs are not opted in. Review firing alerts before any further opt-ins.

`group_by: ['...']` gives each complete alert label set its own group. This avoids
acknowledging one failing instance or workload and masking a different failure.
The supplied rules identify resources using labels such as alertname, cluster,
namespace, pod, instance, and workload. Keep changing values and timestamps in
annotations, never identity labels. Labels must remain stable across repeats.
A changed identity creates a new group; changing grouping later can create new
incidents. Retain the native IRM groupKey and resolved-status templates.

Alertmanager sends resolved notifications and refreshes unchanged firing alerts
every 12 hours. IRM owns immediate notification plus five additional hourly
attempts, six total at 0h through +5h, until ACK. The Alertmanager refresh is not
the user reminder schedule.

The existing kube-prometheus-stack 82.10.5 general rules include
`Watchdog: vector(1)`; general rules are enabled by default and not overridden.
No duplicate rule is added. Watchdog goes only to the native heartbeat receiver
every minute, with no resolved heartbeat. Configure a three-minute IRM heartbeat
timeout after the path is ready. Confirm VMAlert actually evaluates Watchdog
before enabling the heartbeat alarm. This checks rule evaluation, local delivery,
and outbound connectivity, not every scrape target.

## Validation and rollout limits

The Alertmanager Config workflow checks out the exact PR head, renders with the
repository Task command, validates the config with the same Alertmanager image,
and tests routing with offline amtool commands in a container with no network.
Promtool also evaluates 50 offline CNPG scenarios covering healthy primaries,
missing/zero metrics, replicas, mismatched pods and selectors, the five-minute
threshold, recovery and stable database identity. These commands do not create
or send live alerts. Promtool tests standard PromQL semantics, not the live
VictoriaMetrics engine. The existing ArgoCD Diff workflow
compares the affected source and attempts a read-only live diff.

CI rendering does not run the operator, validate admission against installed
CRDs, resolve secret values, or prove delivery and ACK behavior. Before rollout,
verify the installed VMAlertmanager CRD/operator, absence of another Alertmanager,
the Secret's key names without reading values, and the existing Watchdog rule.
No deployment, merge, apply, live configuration, or test alert is authorized here.

This minimal single replica uses the operator's default ephemeral storage.
Pod replacement can lose local silences and the notification log and resend a
firing alert. Native IRM grouping preserves incident identity, but persistence
and availability need separate review before relying on local silences.

After deployment is separately approved, coordinate an end-to-end test:
1. An approved firing alert creates one IRM group and follows the six-attempt
   schedule, unless acknowledged or resolved.
2. ACK stops remaining reminders. Repeated payloads with identical labels retain
   the same group and ACK.
3. A different instance, pod, namespace, or workload creates a different group
   and notifies even while the first is acknowledged.
4. Resolution resolves the matching group.
5. A coordinated loss of Watchdog causes the external heartbeat alarm after
   three minutes and recovery clears it. Do not interrupt monitoring unannounced.

References:
- [VMAlertmanager](https://docs.victoriametrics.com/operator/resources/vmalertmanager/)
- [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Native integration and heartbeat](https://grafana.com/docs/oncall/latest/configure/integrations/references/alertmanager/)
