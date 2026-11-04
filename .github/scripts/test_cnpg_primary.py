#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered CNPG VMRule."""
import json
from pathlib import Path
import sys

import yaml

DATABASES = ("dograh", "kagent", "teslamate")
ALERT = "CNPGPrimaryUnavailable"


def expected(namespace):
    # Independent expected identity: no pod, instance, IP, or collector-only cluster.
    return {
        "exp_labels": {
            "k8s_cluster": "bastion",
            "namespace": namespace,
            "job": f"{namespace}/{namespace}-db",
            "severity": "critical",
            "irm_notify": "true",
        },
        "exp_annotations": {
            "summary": f"No healthy CNPG primary for {namespace}/{namespace}-db",
            "description": "No pod has a successful metrics scrape, healthy collector, and primary role for five minutes. Check database availability and the monitoring path.",
        },
    }


def pod(namespace, *, collector="1+0x12", recovery="0+0x12", scrape="1+0x12",
        name="primary", recovery_pod=None, cluster="bastion", metric_namespace=None,
        endpoint="metrics", container="postgres"):
    labels = {
        "k8s_cluster": cluster,
        "namespace": metric_namespace or namespace,
        "job": f"{namespace}/{namespace}-db",
        "pod": name,
        "container": container,
        "endpoint": endpoint,
        "instance": "10.0.0.1:9187",
    }
    result = []
    for metric, values in [
        ("cnpg_collector_up", collector),
        ("cnpg_pg_replication_in_recovery", recovery),
        ("up", scrape),
    ]:
        if values is None:
            continue
        current = dict(labels)
        if metric == "cnpg_collector_up":
            current["cluster"] = f"{namespace}-db"
        if metric == "cnpg_pg_replication_in_recovery" and recovery_pod:
            current["pod"] = recovery_pod
        selector = ",".join(f"{k}={json.dumps(v)}" for k, v in current.items())
        result.append({"series": metric + "{" + selector + "}", "values": values})
    return result


def check(minute, failures=()):
    return {"eval_time": f"{minute}m", "alertname": ALERT,
            "exp_alerts": [expected(ns) for ns in failures]}


def case(name, series, checks):
    return {"name": name, "interval": "1m", "input_series": series,
            "alert_rule_test": checks}


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(d for d in docs if d and d.get("kind") == "VMRule"
                  and d["metadata"]["name"] == "cnpg-primary-availability")
    rules = vmrule["spec"]["groups"][0]["rules"]
    assert len(rules) == 3
    for namespace, rule in zip(DATABASES, rules):
        assert rule["alert"] == ALERT
        assert rule["for"] == "5m"
        assert rule["labels"] == expected(namespace)["exp_labels"]
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))
    tests = [
        case("all primaries healthy", sum((pod(ns) for ns in DATABASES), []), [check(5), check(10)]),
        case("all databases missing retain three distinct identities", [],
             [check(4), check(5, DATABASES), check(10, DATABASES)]),
    ]
    for ns in DATABASES:
        other = sum((pod(db) for db in DATABASES if db != ns), [])
        for name, data in [
            ("collector zero", pod(ns, collector="0+0x12")),
            ("scrape zero", pod(ns, scrape="0+0x12")),
            ("all series missing", []),
            ("recovery only", pod(ns, recovery="1+0x12")),
            ("collector missing", pod(ns, collector=None)),
            ("scrape missing", pod(ns, scrape=None)),
            ("recovery missing", pod(ns, recovery=None)),
            ("signals from different pods", pod(ns, recovery_pod="replica")),
            ("wrong namespace cannot mask failure", pod(ns, metric_namespace="other")),
            ("wrong cluster cannot mask failure", pod(ns, cluster="other")),
            ("wrong endpoint cannot mask failure", pod(ns, endpoint="other")),
            ("wrong container cannot mask failure", pod(ns, container="other")),
        ]:
            tests.append(case(f"{ns}: {name}", other + data,
                              [check(4), check(5, [ns]), check(10, [ns])]))
        tests.append(case(f"{ns}: healthy primary and replica", other + pod(ns) +
                          pod(ns, name="replica", recovery="1+0x12"), [check(5), check(10)]))
        tests.append(case(f"{ns}: transient shorter than five minutes", other +
                          pod(ns, collector="0+0x3 1+0x8"),
                          [check(3), check(4), check(5), check(10)]))
        tests.append(case(f"{ns}: failure then recovery on the same pod", other +
                          pod(ns, collector="0+0x5 1+0x6"),
                          [check(4), check(5, [ns]), check(6), check(10)]))
        tests.append(case(f"{ns}: primary replacement keeps database identity", other +
                          pod(ns, collector="0+0x5 stale", recovery="0+0x5 stale",
                              scrape="1+0x5 stale") +
                          pod(ns, name="replacement", collector="_ _ _ _ _ _ 1+0x6",
                              recovery="_ _ _ _ _ _ 0+0x6", scrape="_ _ _ _ _ _ 1+0x6"),
                          [check(4), check(5, [ns]), check(6), check(10)]))
    (out / "tests.yml").write_text(yaml.safe_dump({
        "rule_files": ["/fixtures/rules.yml"],
        "evaluation_interval": "1m", "tests": tests,
    }, sort_keys=False))
    print(f"Generated {len(tests)} offline CNPG rule scenarios")


if __name__ == "__main__":
    main()
