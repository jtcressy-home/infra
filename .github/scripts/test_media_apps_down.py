#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered media-apps VMRule."""
from pathlib import Path
import sys

import yaml

MEDIA = "MediaAppDown"
OVERSEERR_ALERT = "OverseerrDown"
APPS_30M = ("sonarr", "radarr", "prowlarr", "sabnzbd", "navidrome", "tautulli")
OVERSEERR = "overseerr"
HOLD = "1+0x45"


def expr_text(rule):
    return " ".join(rule["expr"].split())


def expected(deployment, minutes):
    return {
        "exp_labels": {
            "namespace": "media",
            "deployment": deployment,
            "k8s_cluster": "bastion",
            "severity": "warning",
        },
        "exp_annotations": {
            "summary": f"Media deployment media/{deployment} has no available replicas",
            "description": (
                f"media/{deployment} has had fewer than one available replica "
                f"for {minutes} minutes."
            ),
        },
    }


def sample(deployment, values, namespace="media"):
    return {
        "series": (
            "kube_deployment_status_replicas_available"
            f'{{namespace="{namespace}",deployment="{deployment}"}}'
        ),
        "values": values,
    }


def apps(overrides=None, namespace="media"):
    overrides = overrides or {}
    names = (*APPS_30M, OVERSEERR)
    return [sample(name, overrides.get(name, HOLD), namespace) for name in names]


def check(minute, alertname, failures=()):
    return {
        "eval_time": f"{minute}m",
        "alertname": alertname,
        "exp_alerts": [expected(deployment, minutes) for deployment, minutes in failures],
    }


def quiet(*minutes):
    checks = []
    for minute in minutes:
        checks.append(check(minute, MEDIA))
        checks.append(check(minute, OVERSEERR_ALERT))
    return checks


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
        d for d in docs
        if d and d.get("kind") == "VMRule" and d["metadata"]["name"] == "media-apps-down"
    )
    assert vmrule["metadata"]["namespace"] == "monitoring"
    group = vmrule["spec"]["groups"][0]
    assert group["name"] == "media-apps-down"
    assert group["interval"] == "1m"
    rules = group["rules"]
    assert len(rules) == 2
    slow, fast = rules
    assert slow["alert"] == MEDIA
    assert fast["alert"] == OVERSEERR_ALERT
    assert slow["for"] == "30m"
    assert fast["for"] == "15m"
    slow_expr = expr_text(slow)
    fast_expr = expr_text(fast)
    assert slow_expr == (
        'kube_deployment_status_replicas_available{namespace="media",'
        'deployment=~"sonarr|radarr|prowlarr|sabnzbd|navidrome|tautulli"} < 1'
    )
    assert fast_expr == (
        'kube_deployment_status_replicas_available{namespace="media",deployment="overseerr"} < 1'
    )
    assert "lidarr" not in slow_expr and "lidarr" not in fast_expr
    labels = {"k8s_cluster": "bastion", "severity": "warning"}
    for rule in rules:
        assert rule["labels"] == labels
        assert "irm_notify" not in rule["labels"]
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))
    tests = [
        case("all listed apps have a replica", apps(), quiet(15, 30, 40)),
        case("no series for the listed apps", [], quiet(15, 30, 40)),
        case(
            "lidarr has no replica and is not in this rule",
            apps() + [sample("lidarr", "0+0x45")],
            quiet(15, 30, 40),
        ),
        case(
            "an unlisted media deployment has no replica",
            apps() + [sample("bazarr", "0+0x45")],
            quiet(15, 30, 40),
        ),
        case(
            "the same names outside the media namespace stay quiet",
            apps(namespace="other"),
            quiet(15, 30, 40),
        ),
    ]
    for name in APPS_30M:
        tests.append(case(
            f"{name} below one replica for the 30m window",
            apps({name: "0+0x45"}),
            [
                check(29, MEDIA),
                check(29, OVERSEERR_ALERT),
                check(30, MEDIA, [(name, 30)]),
                check(30, OVERSEERR_ALERT),
                check(40, MEDIA, [(name, 30)]),
                check(40, OVERSEERR_ALERT),
            ],
        ))
    tests.extend([
        case(
            "overseerr uses the 15m window only",
            apps({"overseerr": "0+0x45"}),
            [
                check(14, OVERSEERR_ALERT),
                check(14, MEDIA),
                check(15, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(15, MEDIA),
                check(30, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(30, MEDIA),
                check(40, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(40, MEDIA),
            ],
        ),
        case(
            "overseerr and sonarr pending windows stay independent",
            apps({"overseerr": "0+0x45", "sonarr": "0+0x45"}),
            [
                check(14, OVERSEERR_ALERT),
                check(14, MEDIA),
                check(15, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(15, MEDIA),
                check(29, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(29, MEDIA),
                check(30, OVERSEERR_ALERT, [(OVERSEERR, 15)]),
                check(30, MEDIA, [("sonarr", 30)]),
            ],
        ),
        case(
            "all six 30m apps fire together while overseerr stays up",
            apps({name: "0+0x45" for name in APPS_30M}),
            [
                check(29, MEDIA),
                check(29, OVERSEERR_ALERT),
                check(30, MEDIA, [(name, 30) for name in APPS_30M]),
                check(30, OVERSEERR_ALERT),
                check(40, MEDIA, [(name, 30) for name in APPS_30M]),
                check(40, OVERSEERR_ALERT),
            ],
        ),
        case(
            "sonarr recovers before 30m",
            apps({"sonarr": "0+0x10 1+0x34"}),
            quiet(10, 30, 40),
        ),
        case(
            "overseerr recovers before 15m",
            apps({"overseerr": "0+0x10 1+0x34"}),
            quiet(10, 15, 30),
        ),
    ])
    (out / "tests.yml").write_text(yaml.safe_dump({
        "rule_files": ["/fixtures/rules.yml"],
        "evaluation_interval": "1m",
        "tests": tests,
    }, sort_keys=False))
    print(f"Generated {len(tests)} offline media-app rule scenarios")


if __name__ == "__main__":
    main()
