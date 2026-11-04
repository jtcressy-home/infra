#!/usr/bin/env python3
"""Generate offline promtool fixtures from the rendered CNPG backup-age VMRule."""
import json
from pathlib import Path
import sys

import yaml

DATABASES = ("dograh", "kagent", "teslamate")
AGE_ALERT = "CNPGBackupTooOld"
ABSENT_ALERT = "CNPGBackupMetricAbsent"
AGE_EXPR = (
    'time() - cnpg_collector_last_available_backup_timestamp{k8s_cluster="bastion"} > 30*3600'
)
# Seconds before the test epoch. time() - value is the backup age.
STALE = -(31 * 3600)
EXACT_30H = -(30 * 3600)
UNDER_30H = -(29 * 3600)
# Plan snapshot: about 4.1h on all three databases (4.1 * 3600 = 14760).
LIVE_AGE = -(4 * 3600 + 6 * 60)


def age_expected(namespace, pod=None):
    labels = {
        "k8s_cluster": "bastion",
        "namespace": namespace,
        "job": f"{namespace}/{namespace}-db",
        "severity": "warning",
        "irm_notify": "true",
    }
    if pod:
        labels["pod"] = pod
    return {
        "exp_labels": labels,
        "exp_annotations": {
            "summary": f"CNPG backup for {namespace}/{namespace}-db is older than 30 hours",
            "description": (
                f"The last available backup for {namespace}/{namespace}-db is more than 30 hours old "
                "and has remained so for 30 minutes. Daily backups run just after midnight UTC. "
                "Check the ScheduledBackup and the object-store destination."
            ),
        },
    }


def absent_expected(namespace):
    return {
        "exp_labels": {
            "k8s_cluster": "bastion",
            "namespace": namespace,
            "job": f"{namespace}/{namespace}-db",
            "severity": "warning",
            "irm_notify": "true",
        },
        "exp_annotations": {
            "summary": f"CNPG backup metric missing for {namespace}/{namespace}-db",
            "description": (
                "cnpg_collector_last_available_backup_timestamp has been absent for "
                f"{namespace}/{namespace}-db for one hour, so backup age cannot be evaluated."
            ),
        },
    }


def hold(value, samples):
    return f"{value}+0x{samples - 1}"


def ramp(start, samples):
    return f"{start}+60x{samples - 1}"


def series(namespace, values, *, cluster="bastion", pod=None):
    labels = {
        "k8s_cluster": cluster,
        "namespace": namespace,
        "job": f"{namespace}/{namespace}-db",
    }
    if pod:
        labels["pod"] = pod
    selector = ",".join(f"{k}={json.dumps(v)}" for k, v in labels.items())
    return {
        "series": "cnpg_collector_last_available_backup_timestamp{" + selector + "}",
        "values": values,
    }


def fresh(namespace, samples=100, **kwargs):
    return series(namespace, ramp(0, samples), **kwargs)


def check(minute, alertname, failures=()):
    expected = age_expected if alertname == AGE_ALERT else absent_expected
    alerts = []
    for item in failures:
        if isinstance(item, tuple):
            alerts.append(age_expected(*item))
        else:
            alerts.append(expected(item))
    return {"eval_time": f"{minute}m", "alertname": alertname, "exp_alerts": alerts}


def both(minute, age=(), absent=()):
    return [check(minute, AGE_ALERT, age), check(minute, ABSENT_ALERT, absent)]


def case(name, input_series, checks):
    return {"name": name, "interval": "1m", "input_series": input_series,
            "alert_rule_test": checks}


def main():
    docs = list(yaml.safe_load_all(Path(sys.argv[1]).read_text()))
    vmrule = next(d for d in docs if d and d.get("kind") == "VMRule"
                  and d["metadata"]["name"] == "cnpg-backup-age")
    assert vmrule["metadata"]["namespace"] == "monitoring"
    group = vmrule["spec"]["groups"][0]
    assert group["name"] == "cnpg-backup-age"
    assert group["interval"] == "1m"
    rules = group["rules"]
    assert len(rules) == 4
    age = rules[0]
    assert age["alert"] == AGE_ALERT
    assert age["expr"] == AGE_EXPR
    assert age["for"] == "30m"
    assert age["labels"] == {
        "k8s_cluster": "bastion",
        "severity": "warning",
        "irm_notify": "true",
    }
    for namespace, rule in zip(DATABASES, rules[1:]):
        assert rule["alert"] == ABSENT_ALERT
        assert rule["expr"] == (
            "absent(cnpg_collector_last_available_backup_timestamp"
            f'{{namespace="{namespace}"}})'
        )
        assert rule["for"] == "1h"
        assert rule["labels"] == absent_expected(namespace)["exp_labels"]
        assert rule["annotations"] == absent_expected(namespace)["exp_annotations"]

    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.yml").write_text(yaml.safe_dump(vmrule["spec"], sort_keys=False))

    fresh_all = [fresh(ns) for ns in DATABASES]
    tests = [
        case("fresh backups stay quiet", fresh_all, both(30) + both(31) + both(60)),
        case("verified live age of about 4.1h stays quiet",
             [series(ns, ramp(LIVE_AGE, 80)) for ns in DATABASES],
             both(30) + both(70)),
        case("all backups 31h old page after 30m and are not absent",
             [series(ns, hold(STALE, 80)) for ns in DATABASES],
             both(29) + both(30, age=DATABASES) + both(60, age=DATABASES)),
        case("age of exactly 30h does not page until the next minute holds",
             [series(ns, hold(EXACT_30H, 40)) for ns in DATABASES],
             both(30) + both(31, age=DATABASES)),
        case("age of 29h is still equal to 30h at 60m and pages only at 91m",
             [series(ns, hold(UNDER_30H, 100)) for ns in DATABASES],
             both(60) + both(90) + both(91, age=DATABASES)),
    ]
    for ns in DATABASES:
        others = [fresh(db) for db in DATABASES if db != ns]
        tests.append(case(
            f"{ns}: only this backup is 31h old",
            others + [series(ns, hold(STALE, 80))],
            both(29) + both(30, age=[ns]) + both(60, age=[ns]),
        ))
        tests.append(case(
            f"{ns}: metric missing pages after 1h",
            others,
            both(59) + both(60, absent=[ns]) + both(70, absent=[ns]),
        ))
        tests.append(case(
            f"{ns}: stale for 20m never reaches the 30m hold",
            others + [series(ns, f"{STALE}+0x19 {20 * 60}+60x50")],
            both(19) + both(20) + both(50),
        ))
        tests.append(case(
            f"{ns}: fresh for 10m then 31h old pages at 40m",
            others + [series(ns, f"0+60x9 {STALE}+0x80")],
            both(39) + both(40, age=[ns]) + both(50, age=[ns]),
        ))
        tests.append(case(
            f"{ns}: 31h old recovers at 40m and the page clears",
            others + [series(ns, f"{STALE}+0x39 {40 * 60}+60x40")],
            both(30, age=[ns]) + both(39, age=[ns]) + both(40) + both(70),
        ))

    tests.append(case(
        "dograh missing and kagent stale page on their own clocks",
        [series("kagent", hold(STALE, 80)), fresh("teslamate")],
        both(29) + both(30, age=["kagent"]) + both(59, age=["kagent"])
        + both(60, age=["kagent"], absent=["dograh"]),
    ))
    tests.append(case(
        "a stale and a fresh series for one database page only the stale pod",
        [series("dograh", hold(STALE, 80), pod="stale"),
         series("dograh", ramp(0, 80), pod="fresh"),
         fresh("kagent"), fresh("teslamate")],
        both(29) + both(30, age=[("dograh", "stale")]) + both(60, age=[("dograh", "stale")]),
    ))
    tests.append(case(
        "wrong k8s_cluster does not match the age rule and still satisfies absent",
        [series("dograh", hold(STALE, 80), cluster="other"), fresh("kagent"), fresh("teslamate")],
        both(30) + both(60),
    ))
    tests.append(case(
        "all three metrics missing retain three distinct identities",
        [],
        both(59) + both(60, absent=DATABASES) + both(70, absent=DATABASES),
    ))
    tests.append(case(
        "absent clears when the series returns",
        [series("dograh", " ".join(["stale"] * 70 + [str(70 * 60)])),
         fresh("kagent"), fresh("teslamate")],
        both(59) + both(60, absent=["dograh"]) + both(70),
    ))

    (out / "tests.yml").write_text(yaml.safe_dump({
        "rule_files": ["/fixtures/rules.yml"],
        "evaluation_interval": "1m",
        "tests": tests,
    }, sort_keys=False))
    print(f"Generated {len(tests)} offline CNPG backup-age scenarios")


if __name__ == "__main__":
    main()
