#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered Talos /var VMRule."""
import json
from pathlib import Path
import sys

import yaml

ALERT = "TalosVarFilesystemLow"
EXPR = (
    'node_filesystem_avail_bytes{job="node-exporter",mountpoint="/var"}'
    " / "
    'node_filesystem_size_bytes{job="node-exporter",mountpoint="/var"}'
    " < 0.15"
)
LABELS = {
    "k8s_cluster": "bastion",
    "severity": "critical",
    "irm_notify": "true",
}
ANNOTATIONS = {
    "summary": "Talos node /var filesystem is below 15% free",
    "description": (
        "node-exporter reports /var under 15% free for 30 minutes. "
        "A full /var on talos-master-0 breaks kubelet, containerd, and etcd."
    ),
}
BASE_LABELS = {
    "job": "node-exporter",
    "mountpoint": "/var",
    "instance": "talos-master-0",
    "device": "/dev/nvme0n1p6",
    "fstype": "xfs",
    "k8s_cluster": "bastion",
}


def normalize(expr):
    return " ".join(expr.split())


def selector(labels):
    kept = {key: value for key, value in labels.items() if value is not None}
    return ",".join(f"{key}={json.dumps(value)}" for key, value in kept.items())


def sample(metric, values, **overrides):
    labels = dict(BASE_LABELS)
    labels.update(overrides)
    return {"series": f"{metric}{{{selector(labels)}}}", "values": values}


def fs(avail, size, **overrides):
    series = []
    if avail is not None:
        series.append(sample("node_filesystem_avail_bytes", avail, **overrides))
    if size is not None:
        series.append(sample("node_filesystem_size_bytes", size, **overrides))
    return series


def expected(**overrides):
    labels = dict(BASE_LABELS)
    labels.update(LABELS)
    labels.update(overrides)
    labels = {key: value for key, value in labels.items() if value is not None}
    return {"exp_labels": labels, "exp_annotations": dict(ANNOTATIONS)}


def check(minute, alerts=()):
    return {"eval_time": f"{minute}m", "alertname": ALERT, "exp_alerts": list(alerts)}


def case(name, series, checks):
    return {
        "name": name,
        "interval": "1m",
        "input_series": series,
        "alert_rule_test": checks,
    }


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(
        doc for doc in docs
        if doc and doc.get("kind") == "VMRule" and doc["metadata"]["name"] == "talos-var-low"
    )
    rules = vmrule["spec"]["groups"][0]["rules"]
    assert vmrule["metadata"]["namespace"] == "monitoring"
    assert vmrule["spec"]["groups"][0]["interval"] == "1m"
    assert len(rules) == 1
    rule = rules[0]
    assert rule["alert"] == ALERT
    assert normalize(rule["expr"]) == EXPR
    assert rule["for"] == "30m"
    assert rule["labels"] == LABELS
    assert rule["annotations"] == ANNOTATIONS

    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))

    hold = "1000+0x45"
    firing = [expected()]
    tests = [
        case(
            "35.9 percent free does not fire",
            fs("359+0x45", hold),
            [check(29), check(30), check(45)],
        ),
        case(
            "exactly 15 percent free does not fire",
            fs("150+0x45", hold),
            [check(30), check(45)],
        ),
        case(
            "below 15 percent fires at 30m",
            fs("140+0x45", hold),
            [check(29), check(30, firing), check(45, firing)],
        ),
        case(
            "other mountpoint does not fire",
            fs("10+0x45", hold, mountpoint="/"),
            [check(30), check(45)],
        ),
        case(
            "other job does not fire",
            fs("10+0x45", hold, job="kubelet"),
            [check(30), check(45)],
        ),
        case(
            "dip shorter than 30m does not fire",
            fs("140+0x19 800+0x26", hold),
            [check(19), check(29), check(30), check(45)],
        ),
        case(
            "recovery clears the page",
            fs("140+0x35 800+0x10", hold),
            [check(29), check(30, firing), check(35, firing), check(36), check(45)],
        ),
        case(
            "only the low instance fires",
            fs("140+0x45", hold) + fs("800+0x45", hold, instance="talos-worker-1"),
            [check(29), check(30, firing), check(45, firing)],
        ),
        case(
            "missing size series does not fire",
            fs("140+0x45", None),
            [check(30), check(45)],
        ),
        case(
            "rule label supplies k8s_cluster",
            fs("140+0x45", hold, k8s_cluster=None),
            [check(29), check(30, firing), check(45, firing)],
        ),
        case(
            "mismatched device labels do not pair",
            fs("140+0x45", None) + fs(None, hold, device="/dev/sda1"),
            [check(30), check(45)],
        ),
    ]
    (out / "tests.yml").write_text(yaml.safe_dump({
        "rule_files": ["rules.yml"],
        "evaluation_interval": "1m",
        "tests": tests,
    }, sort_keys=False))
    print(f"Generated {len(tests)} offline Talos /var rule scenarios")


if __name__ == "__main__":
    main()
