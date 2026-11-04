#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered VictoriaLogsDown VMRule."""
from pathlib import Path
import sys

import yaml

ALERT = "VictoriaLogsDown"
JOB = "victoria-logs-victoria-logs-single-server"
EXPR = (
    'up{job="victoria-logs-victoria-logs-single-server"} == 0 '
    "or "
    'absent(up{job="victoria-logs-victoria-logs-single-server"})'
)


def expected_labels():
    return {
        "k8s_cluster": "bastion",
        "namespace": "monitoring",
        "job": JOB,
        "severity": "warning",
    }


def expected_annotations():
    return {
        "summary": "VictoriaLogs is down",
        "description": (
            "The victoria-logs-victoria-logs-single-server scrape has been down "
            "or absent for ten minutes. Check the VictoriaLogs server and its ServiceMonitor."
        ),
    }


def alert(**extra_labels):
    labels = expected_labels()
    labels.update(extra_labels)
    return {"exp_labels": labels, "exp_annotations": expected_annotations()}


def series(values, **extra_labels):
    labels = {"job": JOB, "namespace": "monitoring"}
    labels.update(extra_labels)
    selector = ",".join(f'{k}="{v}"' for k, v in labels.items())
    return {"series": f"up{{{selector}}}", "values": values}


def check(minute, alerts=()):
    return {
        "eval_time": f"{minute}m",
        "alertname": ALERT,
        "exp_alerts": list(alerts),
    }


def case(name, series_list, checks):
    return {
        "name": name,
        "interval": "1m",
        "input_series": series_list,
        "alert_rule_test": checks,
    }


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(
        d
        for d in docs
        if d and d.get("kind") == "VMRule" and d["metadata"]["name"] == "victorialogs-down"
    )
    rules = vmrule["spec"]["groups"][0]["rules"]
    assert vmrule["metadata"]["namespace"] == "monitoring"
    assert vmrule["spec"]["groups"][0]["name"] == "victorialogs-down"
    assert vmrule["spec"]["groups"][0]["interval"] == "1m"
    assert len(rules) == 1
    rule = rules[0]
    assert rule["alert"] == ALERT
    assert rule["for"] == "10m"
    assert " ".join(rule["expr"].split()) == EXPR
    assert rule["labels"] == expected_labels()
    assert "irm_notify" not in rule["labels"]
    assert rule["annotations"] == expected_annotations()

    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rules_path = out / "rules.yml"
    rules_path.write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))
    tests = [
        case(
            "target up does not fire",
            [series("1+0x20")],
            [check(9), check(10), check(20)],
        ),
        case(
            "target down for ten minutes fires, then recovers",
            [series("0+0x10 1+0x10")],
            [check(9), check(10, [alert()]), check(11), check(20)],
        ),
        case(
            "target down stays firing",
            [series("0+0x20")],
            [check(9), check(10, [alert()]), check(20, [alert()])],
        ),
        case(
            "scrape target absent for ten minutes fires",
            [],
            [check(9), check(10, [alert()]), check(20, [alert()])],
        ),
        case(
            "a different job cannot mask or cause this alert",
            [
                series("1+0x20"),
                {"series": 'up{job="other-job",namespace="monitoring"}', "values": "0+0x20"},
            ],
            [check(10), check(20)],
        ),
        case(
            "another job being up does not mask an absent target",
            [{"series": 'up{job="other-job",namespace="monitoring"}', "values": "1+0x20"}],
            [check(9), check(10, [alert()]), check(20, [alert()])],
        ),
        case(
            "only the down instance fires when another instance is up",
            [
                series("0+0x20", instance="10.0.0.1:9428"),
                series("1+0x20", instance="10.0.0.2:9428"),
            ],
            [
                check(9),
                check(10, [alert(instance="10.0.0.1:9428")]),
                check(20, [alert(instance="10.0.0.1:9428")]),
            ],
        ),
        case(
            "dip shorter than ten minutes does not fire",
            [series("1+0x2 0+0x8 1+0x10")],
            [check(2), check(11), check(12), check(20)],
        ),
    ]
    (out / "tests.yml").write_text(
        yaml.safe_dump(
            {
                "rule_files": [str(rules_path.resolve())],
                "evaluation_interval": "1m",
                "tests": tests,
            },
            sort_keys=False,
        )
    )
    print(f"Generated {len(tests)} offline VictoriaLogsDown rule scenarios")


if __name__ == "__main__":
    main()
