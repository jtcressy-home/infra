import base64
import contextlib
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVENT = "monitoring.incident_changed"
HOUR = 3600
RETENTION = 7 * 86400
MAX_EVENTS = 50000
MAX_OUTBOX = 200000


class Invalid(ValueError):
    pass


class Capacity(OSError):
    pass


class Conflict(Invalid):
    pass


class Denied(Invalid):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(value):
    return (
        datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    )


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.timestamp()
    except (TypeError, ValueError, AttributeError):
        raise Invalid("expected a timestamp with timezone") from None


def cursor(seq):
    return base64.urlsafe_b64encode(f"v1:{seq}".encode()).decode().rstrip("=")


def sequence(value):
    if value is None:
        return None
    try:
        text = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        if not re.fullmatch(r"v1:[0-9]+", text):
            raise ValueError()
        return int(text[3:])
    except Exception:
        raise Invalid("invalid cursor") from None


class Store:
    def __init__(self, path, clock=time.time):
        self.path = path
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        if path != ":memory:":
            Path(path).chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, episode TEXT UNIQUE, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, at REAL, incident TEXT, kind TEXT, body TEXT);
        CREATE INDEX IF NOT EXISTS events_incident_kind_seq ON events(incident,kind,seq);
        CREATE TABLE IF NOT EXISTS subscriptions(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(seq INTEGER, dest TEXT, state TEXT, attempts INTEGER DEFAULT 0,
          due REAL, lease REAL DEFAULT 0, receipt TEXT, PRIMARY KEY(seq,dest));
        CREATE TABLE IF NOT EXISTS requests(principal TEXT, id TEXT, fingerprint TEXT, result TEXT, at REAL, PRIMARY KEY(principal,id));
        CREATE TABLE IF NOT EXISTS seen(principal TEXT, event TEXT, at REAL, PRIMARY KEY(principal,event));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """)

        columns = {row[1] for row in self.db.execute("PRAGMA table_info(outbox)")}
        if "attempt_token" not in columns:
            self.db.execute("ALTER TABLE outbox ADD COLUMN attempt_token TEXT")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS receipts(token TEXT PRIMARY KEY, seq INTEGER, dest TEXT, at REAL, status INTEGER, receipt TEXT)"
        )

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        self.db.execute(
            "INSERT OR REPLACE INTO meta VALUES (?,?)", (key, canonical(value))
        )

    def incidents(self):
        with self.lock:
            return [
                json.loads(r[0])
                for r in self.db.execute("SELECT data FROM incidents ORDER BY id")
            ]

    def read(self, iid):
        row = self.db.execute(
            "SELECT data FROM incidents WHERE id=?", (iid,)
        ).fetchone()
        if row is None:
            raise Invalid("unknown incident")
        return json.loads(row[0])

    def save(self, item):
        self.db.execute(
            "INSERT OR REPLACE INTO incidents VALUES (?,?,?)",
            (item["id"], item["episode"], canonical(item)),
        )

    def subscriptions(self):
        return [
            json.loads(r[0]) for r in self.db.execute("SELECT data FROM subscriptions")
        ]

    def save_subscription(self, sub):
        self.db.execute(
            "INSERT OR REPLACE INTO subscriptions VALUES (?,?)",
            (sub["id"], canonical(sub)),
        )

    def emit(self, item, kind):
        now = self.clock()
        if (
            self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= MAX_EVENTS
            or self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
            + 1
            + sum(
                sub["active"] and sub["expires"] > now for sub in self.subscriptions()
            )
            > MAX_OUTBOX
        ):
            raise Capacity("delivery journal capacity reached")
        item["revision"] += 1
        data = {
            "incident_id": item["id"],
            "revision": item["revision"],
            "kind": kind,
            "severity": item["severity"],
            "summary": item["summary"],
            "observed_at": iso(now),
        }
        if item.get("ack") and item["ack"].get("jira_url"):
            data["jira_url"] = item["ack"]["jira_url"]
        eid = str(uuid.uuid4())
        body = {"eventId": eid, "name": EVENT, "timestamp": iso(now), "data": data}
        seq = self.db.execute(
            "INSERT INTO events(id,at,incident,kind,body) VALUES (?,?,?,?,?)",
            (eid, now, item["id"], kind, "{}"),
        ).lastrowid
        body["cursor"] = cursor(seq)
        self.db.execute("UPDATE events SET body=? WHERE seq=?", (canonical(body), seq))
        self.db.execute(
            "INSERT INTO outbox(seq,dest,state,due) VALUES (?,?,?,?)",
            (seq, "discord", "pending", now),
        )
        for sub in self.subscriptions():
            if sub["active"] and sub["expires"] > now:
                self.db.execute(
                    "INSERT INTO outbox(seq,dest,state,due) VALUES (?,?,?,?)",
                    (seq, sub["id"], "pending", now),
                )
        self.save(item)

    def cancel(self, iid):
        self.db.execute(
            "UPDATE outbox SET state='cancelled' WHERE state IN ('pending','leased') AND seq IN (SELECT seq FROM events WHERE incident=? AND kind IN ('opened','reminder'))",
            (iid,),
        )

    def validate_alerts(self, alerts):
        now = self.clock()
        if not isinstance(alerts, list) or len(alerts) > 5000:
            raise Invalid("invalid alerts array")
        result = []
        for alert in alerts:
            if not isinstance(alert, dict) or alert.get("status") not in (
                "firing",
                "resolved",
            ):
                raise Invalid("invalid per-alert status")
            labels = alert.get("labels")
            fp = alert.get("fingerprint")
            if (
                not isinstance(labels, dict)
                or labels.get("cluster") != "bastion"
                or len(labels) > 100
                or not all(
                    isinstance(k, str)
                    and isinstance(v, str)
                    and len(k) <= 256
                    and len(v) <= 2048
                    for k, v in labels.items()
                )
                or not isinstance(fp, str)
                or not re.fullmatch(r"[a-fA-F0-9]{1,64}", fp)
            ):
                raise Invalid("invalid labels or fingerprint")
            onset = timestamp(alert.get("startsAt"))
            if onset > now + 60 or onset < 0:
                raise Invalid("invalid onset")
            end = (
                timestamp(alert.get("endsAt"))
                if alert["status"] == "resolved"
                else None
            )
            if end is not None and (end < onset or end > now + 60):
                raise Invalid("invalid resolution time")
            result.append((fp.lower(), onset, end, dict(labels), alert["status"]))
        return result

    def ingest(self, body):
        if not isinstance(body, dict) or body.get("version") != "4":
            raise Invalid("expected Alertmanager webhook version 4")
        truncated = body.get("truncatedAlerts", 0)
        if type(truncated) is not int or truncated < 0:
            raise Invalid("invalid truncation count")
        records = self.validate_alerts(body.get("alerts"))
        with self.transaction():
            self.apply(
                records, healthy=self.get_meta("health_until", 0) >= self.clock()
            )
            self.set_meta("last_webhook", self.clock())
            if truncated:
                self.set_meta("truncated_at", self.clock())
        return {"accepted": len(records), "incomplete": bool(truncated)}

    def apply(self, records, healthy):
        now = self.clock()
        for fp, onset, end, labels, status in records:
            episode = hashlib.sha256(
                canonical(["alertmanager", fp, onset]).encode()
            ).hexdigest()
            row = self.db.execute(
                "SELECT data FROM incidents WHERE episode=?", (episode,)
            ).fetchone()
            if row:
                item = json.loads(row[0])
                # An already-resolved episode stays closed even after a delayed firing POST.
                if item["state"] == "recovered":
                    continue
            else:
                if (
                    self.db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
                    >= 10000
                ):
                    raise Capacity("incident capacity reached")
                item = {
                    "id": str(uuid.uuid4()),
                    "episode": episode,
                    "fingerprint": fp,
                    "onset": onset,
                    "first_observed": now,
                    "labels": labels,
                    "revision": 0,
                    "state": "firing",
                    "severity": "warning",
                    "summary": "Monitoring alert: "
                    + re.sub(
                        r"[^a-zA-Z0-9_.:-]", "_", labels.get("alertname", "unnamed")
                    )[:160],
                    "ack": None,
                    "snooze_until": 0,
                    "next_reminder": onset
                    + (max(0, math.floor((now - onset) / HOUR)) + 1) * HOUR,
                    "missing_count": 0,
                    "pending_resolution": None,
                }
                if status == "resolved":
                    # Tombstone prevents an old firing delivery from reopening a closed episode.
                    item["state"] = "recovered" if healthy else "unknown"
                    item["pending_resolution"] = end
                    self.save(item)
                    if not healthy:
                        self.emit(item, "monitoring_unknown")
                    continue
                item["severity"] = (
                    "critical" if labels.get("severity") == "critical" else "warning"
                )
                self.emit(item, "opened")
            if status == "resolved":
                item["pending_resolution"] = end
                if healthy:
                    item["state"] = "recovered"
                    item["recovered_at"] = now
                    self.cancel(item["id"])
                    self.emit(item, "recovered")
                elif item["state"] != "unknown":
                    item["state"] = "unknown"
                    self.emit(item, "monitoring_unknown")
            else:
                item["missing_count"] = 0
                if healthy:
                    item["state"] = "firing"
                if (
                    labels.get("severity") == "critical"
                    and item["severity"] != "critical"
                ):
                    item["severity"] = "critical"
                    self.emit(item, "worsened")
            self.save(item)

    def reconcile(self, alerts, healthy):
        records = self.validate_alerts(alerts)
        with self.transaction():
            now = self.clock()
            self.set_meta("health_until", now + 90 if healthy else 0)
            self.set_meta("last_reconcile", now)
            self.apply(records, healthy=healthy)
            active = {
                (fp, onset) for fp, onset, _, _, status in records if status == "firing"
            }
            for item in self.incidents():
                if item["state"] == "recovered":
                    continue
                present = (item["fingerprint"], item["onset"]) in active
                if not healthy:
                    item["missing_count"] = 0
                    if item["state"] != "unknown":
                        item["state"] = "unknown"
                        self.emit(item, "monitoring_unknown")
                elif not present:
                    if now - item.get("last_absent_check", 0) >= 30:
                        item["missing_count"] += 1
                        item["last_absent_check"] = now
                    if (
                        item["pending_resolution"] is not None
                        or item["missing_count"] >= 2
                    ):
                        item["state"] = "recovered"
                        item["recovered_at"] = now
                        self.cancel(item["id"])
                        self.emit(item, "recovered")
                else:
                    item["missing_count"] = 0
                    item["state"] = "firing"
                self.save(item)

    def tick(self):
        self.prune()
        with self.transaction():
            now = self.clock()
            for item in self.incidents():
                if item["state"] == "recovered":
                    continue
                if (
                    self.get_meta("health_until", 0) < now
                    and item["state"] != "unknown"
                ):
                    item["state"] = "unknown"
                    item["missing_count"] = 0
                    self.emit(item, "monitoring_unknown")
                if (
                    not item["ack"]
                    and item["snooze_until"] <= now
                    and item["next_reminder"] <= now
                ):
                    # Coalesce old unsent reminders in both destinations before making one current slot.
                    self.db.execute(
                        "UPDATE outbox SET state='cancelled' WHERE state IN ('pending','leased') AND seq IN (SELECT seq FROM events WHERE incident=? AND kind='reminder')",
                        (item["id"],),
                    )
                    self.emit(item, "reminder")
                    item["next_reminder"] = (
                        item["onset"]
                        + (math.floor((now - item["onset"]) / HOUR) + 1) * HOUR
                    )
                    self.save(item)

    def prune(self):
        with self.transaction():
            now = self.clock()
            # Retained journal is bounded. Expired undelivered records become an
            # observable loss counter, never accepted receipts; replay reports a gap.
            cutoff = now - RETENTION
            self.db.execute("DELETE FROM receipts WHERE at<?", (cutoff,))
            old = self.db.execute(
                "SELECT MAX(seq) FROM events WHERE at < ?", (cutoff,)
            ).fetchone()[0]
            if old is not None:
                lost = self.db.execute(
                    "SELECT COUNT(*) FROM outbox WHERE seq<=? AND state NOT IN ('accepted','cancelled')",
                    (old,),
                ).fetchone()[0]
                self.set_meta(
                    "expired_deliveries", self.get_meta("expired_deliveries", 0) + lost
                )
                self.set_meta("journal_floor", old)
                self.db.execute("DELETE FROM outbox WHERE seq<=?", (old,))
                self.db.execute("DELETE FROM events WHERE seq<=?", (old,))
            self.db.execute(
                "DELETE FROM seen WHERE event NOT IN (SELECT id FROM events)"
            )
            self.db.execute("DELETE FROM requests WHERE at<?", (cutoff,))
            for item in self.incidents():
                if (
                    item["state"] == "recovered"
                    and item.get("recovered_at", item["first_observed"])
                    < now - 30 * 86400
                ):
                    self.db.execute("DELETE FROM incidents WHERE id=?", (item["id"],))
            for sub in self.subscriptions():
                if sub["expires"] < cutoff:
                    self.db.execute(
                        "DELETE FROM subscriptions WHERE id=?", (sub["id"],)
                    )
                    self.db.execute("DELETE FROM outbox WHERE dest=?", (sub["id"],))

    def source_fault(self):
        with self.transaction():
            existing = [
                x
                for x in self.incidents()
                if x.get("origin") == "source_health" and x["state"] != "recovered"
            ]
            if existing:
                return
            now = self.clock()
            item = {
                "id": str(uuid.uuid4()),
                "episode": "source-health:" + str(now),
                "origin": "source_health",
                "fingerprint": "internal",
                "onset": now,
                "first_observed": now,
                "labels": {},
                "revision": 0,
                "state": "unknown",
                "severity": "critical",
                "summary": "Monitoring source health is unknown",
                "ack": None,
                "snooze_until": 0,
                "next_reminder": now + HOUR,
                "missing_count": 0,
                "pending_resolution": None,
            }
            self.emit(item, "monitoring_unknown")

    def command(self, principal, method, args, jira_origin):
        rid = args.get("request_id")
        if not isinstance(rid, str) or not 1 <= len(rid) <= 128:
            raise Invalid("request_id required")
        digest = hashlib.sha256(canonical([method, args]).encode()).hexdigest()
        with self.transaction():
            old = self.db.execute(
                "SELECT fingerprint,result FROM requests WHERE principal=? AND id=?",
                (principal["id"], rid),
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise Conflict("request_id already used for different input")
                return json.loads(old[1])
            if self.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] >= 100000:
                raise Capacity("idempotency journal capacity reached")
            item = self.read(args.get("incident_id"))
            if (
                type(args.get("expected_revision")) is not int
                or args["expected_revision"] != item["revision"]
            ):
                raise Conflict("stale incident revision")
            if method == "ack_incident":
                evidence = args.get("ticket")
                if principal["kind"] == "agent" or evidence is not None:
                    if (
                        not isinstance(evidence, dict)
                        or set(evidence)
                        != {"key", "url", "verified_at", "comment_id", "incident_id"}
                        or len(str(evidence.get("key", ""))) > 32
                        or len(str(evidence.get("comment_id", ""))) > 32
                        or not re.fullmatch(r"OPS-[1-9][0-9]*", evidence.get("key", ""))
                    ):
                        raise Invalid("verified OPS ticket evidence required")
                    if (
                        evidence.get("url")
                        != jira_origin.rstrip("/") + "/browse/" + evidence["key"]
                    ):
                        raise Invalid(
                            "ticket URL does not match configured Jira origin"
                        )
                    verified = timestamp(evidence.get("verified_at"))
                    if (
                        not self.clock() - 900 <= verified <= self.clock() + 30
                        or not re.fullmatch(
                            r"[1-9][0-9]*", str(evidence.get("comment_id", ""))
                        )
                    ):
                        raise Invalid(
                            "fresh ticket read-back and evidence comment required"
                        )
                    if evidence.get("incident_id") != item["id"]:
                        raise Invalid("ticket correlation mismatch")
                item["ack"] = {
                    "principal": principal["id"],
                    "actor_type": principal["kind"],
                    "at": iso(self.clock()),
                    "jira_url": evidence["url"] if evidence else None,
                    "ticket": evidence,
                    "assertion": "caller-verified" if evidence else "human-ack",
                }
                self.cancel(item["id"])
            elif method == "snooze_incident":
                until = timestamp(args.get("until"))
                if not self.clock() < until <= self.clock() + 86400:
                    raise Invalid("snooze must end within 24 hours")
                item["snooze_until"] = until
                self.cancel(item["id"])
            elif method == "rearm_incident":
                item["ack"] = None
                item["snooze_until"] = 0
            else:
                raise Invalid("unknown write tool")
            item["revision"] += 1
            self.save(item)
            result = {"incident": item}
            self.db.execute(
                "INSERT INTO requests VALUES (?,?,?,?,?)",
                (principal["id"], rid, digest, canonical(result), self.clock()),
            )
            return result
