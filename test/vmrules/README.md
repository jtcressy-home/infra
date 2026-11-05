# VMRule tests

`go test ./...` discovers every `VMRule` under `kubernetes/deploy`, extracts its rule groups, and checks them with promtool `3.5.0` (`promtool check rules`). A manifest with no fixture is still syntax-checked.

Behavior tests are a promtool [unit test file](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/) next to the manifest. `cnpg-backup-age-rules_test.yaml` is the example. Rules that do not have a fixture yet, including `cnpg-primary-rules.yaml`, are syntax-checked only. Alertmanager route tests stay in `.github/workflows/alertmanager-config.yml`.

## Add tests for a rule

1. Put one `VMRule` in its own manifest, for example `my-rules.yaml`, with `metadata.name`, `metadata.namespace`, and at least one group. `apiVersion` must be `operator.victoriametrics.com/...`.
2. Add `my-rules_test.yaml` in the same directory (or `my-rules_test.yml`, but not both). Use promtool's test shape: `evaluation_interval`, `tests`, `input_series`, and `alert_rule_test` with `exp_alerts`. Do not set `rule_files`. The runner writes the manifest's groups to `rules.yml` and injects that path.
3. Install promtool 3.5.0, or point `PROMTOOL` at that binary, and run:

```sh
cd test/vmrules
GOWORK=off go test ./...
```

`GOWORK=off` keeps this module separate from the repo `go.work`, which is the magefiles workspace.

The official archive is `prometheus-3.5.0.linux-amd64.tar.gz`, sha256 `e811827af26d822afb09a4f28314f61b618b12cff5369835a67f674d8b46f39a`.

`.github/workflows/vmrules.yml` runs the same command on pull requests that change `kubernetes/deploy`, this module, or the workflow.
