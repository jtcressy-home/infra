#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered remote-access VMRule."""
import json
from pathlib import Path
import sys

import yaml

STATIC_LABELS = {
    "k8s_cluster": "bastion",
    "severity": "critical",
    "irm_notify": "true",
}

RULES = (
    {
        "alert": "TsidpDown",
        "expr": 'kube_deployment_status_replicas_available{namespace="tailscale",deployment="tsidp"} < 1',
        "for": "5m",
        "metric": "kube_deployment_status_replicas_available",
        "identity": {"namespace": "tailscale", "deployment": "tsidp"},
        "summary": "tsidp has no available replicas",
        "description": "Deployment tailscale/tsidp has had fewer than one available replica for five minutes. Tailnet identity and Funnel OIDC depend on it.",
    },
    {
        "alert": "SkylightMcpDown",
        "expr": 'kube_statefulset_status_replicas_ready{namespace="metamcp",statefulset="skylight-mcp"} < 1',
        "for": "10m",
        "metric": "kube_statefulset_status_replicas_ready",
        "identity": {"namespace": "metamcp", "statefulset": "skylight-mcp"},
        "summary": "skylight-mcp has no ready replicas",
        "description": "StatefulSet metamcp/skylight-mcp has had fewer than one ready replica for ten minutes.",
    },
    {
        "alert": "TailscaleProxyDown",
        "expr": 'kube_statefulset_status_replicas_ready{namespace="tailscale",statefulset=~"ts-.*"} < 1',
        "for": "10m",
        "metric": "kube_statefulset_status_replicas_ready",
        "identity": {"namespace": "tailscale", "statefulset": "ts-proxy"},
        "summary": 'Tailscale proxy {{ $labels.statefulset }} has no ready replicas',
        "description": 'StatefulSet tailscale/{{ $labels.statefulset }} has had fewer than one ready replica for ten minutes.',
    },
    {
        "alert": "CloudflaredDown",
        "expr": 'kube_daemonset_status_number_available{namespace="kube-system",daemonset="cloudflared"} < 1',
        "for": "5m",
        "metric": "kube_daemonset_status_number_available",
        "identity": {"namespace": "kube-system", "daemonset": "cloudflared"},
        "summary": "cloudflared has no available pods",
        "description": "DaemonSet kube-system/cloudflared has had fewer than one available pod for five minutes.",
    },
)


def series(metric, labels, values):
    selector = ",".join(f"{key}={json.dumps(value)}" for key, value in labels.items())
    return {"series": f"{metric}{{{selector}}}", "values": values}


def expanded(rule, labels):
    summary = rule["summary"]
    description = rule["description"]
    if rule["alert"] == "TailscaleProxyDown":
        name = labels["statefulset"]
        summary = f"Tailscale proxy {name} has no ready replicas"
        description = (
            f"StatefulSet tailscale/{name} has had fewer than one ready replica for ten minutes."
        )
    return {
        "exp_labels": dict(labels, **STATIC_LABELS),
        "exp_annotations": {"summary": summary, "description": description},
    }


def check(minute, firing=None):
    """firing maps an alertname to the series-label dicts that must be active."""
    firing = firing or {}
    checks = []
    for rule in RULES:
        alerts = firing.get(rule["alert"], ())
        checks.append({
            "eval_time": f"{minute}m",
            "alertname": rule["alert"],
            "exp_alerts": [expanded(rule, labels) for labels in alerts],
        })
    return checks


def case(name, samples, checks):
    return {
        "name": name,
        "interval": "1m",
        "input_series": samples,
        "alert_rule_test": checks,
    }


def healthy_samples(overrides=()):
    """One healthy series per rule, with any (metric, labels, values) replacements applied."""
    samples = []
    replaced = set()
    for metric, labels, values in overrides:
        samples.append(series(metric, labels, values))
        replaced.add((metric, tuple(sorted(labels.items()))))
    for rule in RULES:
        key = (rule["metric"], tuple(sorted(rule["identity"].items())))
        if key in replaced:
            continue
        samples.append(series(rule["metric"], rule["identity"], "1+0x20"))
    return samples


def assert_rule(actual, expected):
    assert actual["alert"] == expected["alert"]
    assert actual["expr"].strip() == expected["expr"]
    assert actual["for"] == expected["for"]
    assert actual["labels"] == STATIC_LABELS
    assert actual["annotations"] == {
        "summary": expected["summary"],
        "description": expected["description"],
    }


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(
        doc for doc in docs
        if doc and doc.get("kind") == "VMRule" and doc["metadata"]["name"] == "remote-access-down"
    )
    assert vmrule["metadata"]["namespace"] == "monitoring"
    group = vmrule["spec"]["groups"][0]
    assert group["name"] == "remote-access-down"
    assert group["interval"] == "1m"
    assert len(group["rules"]) == len(RULES)
    for actual, expected in zip(group["rules"], RULES):
        assert_rule(actual, expected)

    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))

    tests = [
        case("all four workloads healthy", healthy_samples(), sum((
            check(4), check(5), check(9), check(10), check(15),
        ), [])),
        case("series absent does not page", [], sum((
            check(5), check(10), check(15),
        ), [])),
    ]

    for rule in RULES:
        identity = rule["identity"]
        metric = rule["metric"]
        alert = rule["alert"]
        pending = int(rule["for"][:-1]) - 1
        active = int(rule["for"][:-1])
        tests.append(case(
            f"{alert}: below 1 pages after {rule['for']}",
            healthy_samples([(metric, identity, "0+0x20")]),
            sum((
                check(pending),
                check(active, {alert: [identity]}),
                check(15, {alert: [identity]}),
            ), []),
        ))
        tests.append(case(
            f"{alert}: outage shorter than {rule['for']} does not page",
            healthy_samples([(metric, identity, f"0+0x{pending} 1+0x16")]),
            sum((check(pending), check(active), check(15)), []),
        ))
        wrong_namespace = dict(identity, namespace="other")
        tests.append(case(
            f"{alert}: a different namespace does not page",
            healthy_samples([(metric, wrong_namespace, "0+0x20")]),
            sum((check(active), check(15)), []),
        ))
        # 1+0x2 stays up at t=0,1,2. The zero starts at t=3, so `for` elapses at t=3+for.
        down_at = 3
        tests.append(case(
            f"{alert}: outage starts at 3m and pages once {rule['for']} elapses",
            healthy_samples([(metric, identity, "1+0x2 0+0x20")]),
            sum((
                check(down_at + pending),
                check(down_at + active, {alert: [identity]}),
                check(down_at + active + 5, {alert: [identity]}),
            ), []),
        ))

    proxy = RULES[2]
    ts_a = {"namespace": "tailscale", "statefulset": "ts-a"}
    ts_b = {"namespace": "tailscale", "statefulset": "ts-b"}
    tests.append(case(
        "TailscaleProxyDown: each ts-* proxy pages and other names do not",
        healthy_samples([
            (proxy["metric"], ts_a, "0+0x20"),
            (proxy["metric"], ts_b, "0+0x20"),
            (proxy["metric"], {"namespace": "tailscale", "statefulset": "ts-healthy"}, "1+0x20"),
            (proxy["metric"], {"namespace": "tailscale", "statefulset": "not-ts"}, "0+0x20"),
            (proxy["metric"], {"namespace": "tailscale", "statefulset": "foo-ts-bar"}, "0+0x20"),
            (proxy["metric"], {"namespace": "tailscale", "statefulset": "tsidp"}, "0+0x20"),
            (proxy["metric"], {"namespace": "other", "statefulset": "ts-other"}, "0+0x20"),
        ]),
        sum((
            check(9),
            check(10, {proxy["alert"]: [ts_a, ts_b]}),
            check(15, {proxy["alert"]: [ts_a, ts_b]}),
        ), []),
    ))
    tests.append(case(
        "TsidpDown: a different deployment does not page",
        healthy_samples([(
            RULES[0]["metric"],
            {"namespace": "tailscale", "deployment": "other"},
            "0+0x20",
        )]),
        sum((check(5), check(10)), []),
    ))

    (out / "tests.yml").write_text(yaml.safe_dump({
        "rule_files": ["/fixtures/rules.yml"],
        "evaluation_interval": "1m",
        "tests": tests,
    }, sort_keys=False))
    print(f"Generated {len(tests)} offline remote-access rule scenarios")


if __name__ == "__main__":
    main()
