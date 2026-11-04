#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered external-dns VMRule."""
from pathlib import Path
import sys

import yaml

ALERT = "ExternalDNSSyncStale"
EXPR = "time() - external_dns_controller_last_sync_timestamp_seconds > 1800"
METRIC = "external_dns_controller_last_sync_timestamp_seconds"
SUMMARY = "external-dns last successful sync is older than 30 minutes"
DESCRIPTION = (
    "external-dns has not completed a successful DNS sync for 30 minutes, "
    "and that has continued for 10 minutes. Records from Ingress and Service "
    "sources may be stale."
)


def expected(pod="external-dns-unifi-0"):
    return {
        "exp_labels": {
            "k8s_cluster": "bastion",
            "namespace": "kube-system",
            "job": "external-dns-unifi",
            "pod": pod,
            "severity": "warning",
        },
        "exp_annotations": {
            "summary": SUMMARY,
            "description": DESCRIPTION,
        },
    }


def series(values, pod="external-dns-unifi-0"):
    return {
        "series": (
            f'{METRIC}{{namespace="kube-system",job="external-dns-unifi",pod="{pod}"}}'
        ),
        "values": values,
    }


def check(minute, pods=()):
    return {
        "eval_time": f"{minute}m",
        "alertname": ALERT,
        "exp_alerts": [expected(pod) for pod in pods],
    }


def case(name, samples, checks):
    return {
        "name": name,
        "interval": "1m",
        "input_series": samples,
        "alert_rule_test": checks,
    }


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(
        d
        for d in docs
        if d and d.get("kind") == "VMRule" and d["metadata"]["name"] == "external-dns-sync-stale"
    )
    assert vmrule["metadata"]["namespace"] == "monitoring"
    group = vmrule["spec"]["groups"][0]
    assert group["name"] == "external-dns-sync-stale"
    assert group["interval"] == "1m"
    rules = group["rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["alert"] == ALERT
    assert rule["expr"].strip() == EXPR
    assert rule["for"] == "10m"
    assert rule["labels"] == {"k8s_cluster": "bastion", "severity": "warning"}
    assert "irm_notify" not in rule["labels"]
    assert rule["annotations"] == {"summary": SUMMARY, "description": DESCRIPTION}
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))
    # time() is the sample timestamp. A value of t-age makes the sync age constant.
    fresh = "0+60x40"
    age_1800 = "-1800+60x40"
    age_1801 = "-1801+60x40"
    # Stale on samples 0..8 (through 8m), fresh from 9m. Shorter than the 10m for.
    recovers = "-1801+60x8 540+60x31"
    tests = [
        case("fresh sync", [series(fresh)], [check(9), check(10), check(30)]),
        case("age of exactly 1800s stays quiet", [series(age_1800)], [check(10), check(30)]),
        case(
            "age of 1801s fires after 10m",
            [series(age_1801)],
            [check(9), check(10, ["external-dns-unifi-0"]), check(20, ["external-dns-unifi-0"])],
        ),
        case("stale for 9m then fresh does not fire", [series(recovers)], [check(9), check(10), check(20)]),
        case("absent series does not fire", [], [check(10), check(30)]),
        case(
            "only the stale controller fires",
            [series(fresh, pod="external-dns-unifi-a"), series(age_1801, pod="external-dns-unifi-b")],
            [check(9), check(10, ["external-dns-unifi-b"]), check(20, ["external-dns-unifi-b"])],
        ),
    ]
    (out / "tests.yml").write_text(
        yaml.safe_dump(
            {
                "rule_files": ["/fixtures/rules.yml"],
                "evaluation_interval": "1m",
                "tests": tests,
            },
            sort_keys=False,
        )
    )
    print(f"Generated {len(tests)} offline external-dns rule scenarios")


if __name__ == "__main__":
    main()
