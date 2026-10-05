import base64
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cryptography.fernet import Fernet
from standardwebhooks import Webhook
from incident_adapter.store import (
    Store,
    Invalid,
    Conflict,
    Denied,
    iso,
    canonical,
    cursor,
    EVENT,
)
from incident_adapter.events import Events
from incident_adapter.server import API, handler
from incident_adapter.sources import Sources
from incident_adapter.transport import PublicHTTPS
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRINCIPAL = {
    "id": "fixture-agent",
    "kind": "agent",
    "scopes": {"monitoring:read", "monitoring:ack"},
}
HUMAN = {
    "id": "fixture-human",
    "kind": "human",
    "scopes": {"monitoring:read", "monitoring:ack"},
}
SECRET = "whsec_" + base64.b64encode(b"synthetic-test-key-not-production").decode()
DISCORD = "https://discord.com/api/webhooks/synthetic/synthetic"
JIRA = "https://jira.example.invalid"


class Clock:
    def __init__(self):
        self.now = float(int(time.time()))

    def __call__(self):
        return self.now

    def advance(self, n):
        self.now += n


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.status = 200
        self.on_send = None
        self.challenge_ok = True
        self.discord_status = 200

    def request(self, url, body, headers):
        value = json.loads(body)
        self.calls.append((url, value, headers, body))
        if value.get("type") == "verification":
            return (
                200,
                {},
                canonical(
                    {"challenge": value["challenge"] if self.challenge_ok else "wrong"}
                ).encode(),
            )
        if self.on_send:
            self.on_send()
        status = self.discord_status if "discord.com" in url else self.status
        return status, {}, b'{"id":"synthetic-receipt"}'


class FakeAuth:
    issuer = "https://issuer.example.invalid"

    def authenticate(self, header):
        if header != "Bearer synthetic":
            raise Denied("denied")
        return PRINCIPAL


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.path = str(Path(self.tmp.name) / "state.sqlite")
        self.store = Store(self.path, self.clock)
        self.key = Fernet.generate_key()
        self.transport = FakeTransport()
        self.grant = True
        self.events = Events(
            self.store, self.key, self.transport, lambda *_: self.grant, DISCORD
        )
        self.api = API(
            self.store,
            self.events,
            FakeAuth(),
            "synthetic-hook-token-24-characters",
            JIRA,
            "https://adapter.example.invalid/mcp",
        )
        with self.store.transaction():
            self.store.set_meta("health_until", self.clock() + 90)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def alert(self, status="firing", fp="abcd", onset=None, severity="warning"):
        return {
            "status": status,
            "fingerprint": fp,
            "labels": {
                "cluster": "bastion",
                "alertname": "DatabaseUnavailable",
                "severity": severity,
            },
            "startsAt": iso(self.clock() if onset is None else onset),
            "endsAt": iso(self.clock()),
        }

    def ingest(self, *alerts, **kw):
        return self.store.ingest(
            {
                "version": "4",
                "alerts": list(alerts),
                "truncatedAlerts": kw.get("truncated", 0),
            }
        )

    def incident(self):
        return self.store.incidents()[0]

    def subscribe(self, **kw):
        args = {
            "name": EVENT,
            "arguments": {"cluster": "bastion"},
            "delivery": {
                "mode": "webhook",
                "url": "https://receiver.example.invalid/callback",
                "secret": SECRET,
            },
        }
        args.update(kw)
        result = self.events.subscribe(PRINCIPAL, args)
        return result, args

    def command(self, name="ack_incident", principal=PRINCIPAL, **extras):
        item = self.incident()
        args = {
            "incident_id": item["id"],
            "expected_revision": item["revision"],
            "request_id": "request-" + name,
        }
        args.update(extras)
        return self.store.command(principal, name, args, JIRA)

    def evidence(self):
        return {
            "key": "OPS-42",
            "url": JIRA + "/browse/OPS-42",
            "verified_at": iso(self.clock()),
            "comment_id": "123",
            "incident_id": self.incident()["id"],
        }

    def drain(self):
        for _ in range(30):
            if not self.events.deliver_one():
                return
        self.fail("outbox did not drain")

    def rows(self):
        return [dict(r) for r in self.store.db.execute("SELECT * FROM outbox")]

    def test_duplicate_and_restart_preserve_onset_and_ids(self):
        alert = self.alert()
        self.ingest(alert)
        original = self.incident()
        self.clock.advance(100)
        self.ingest(alert)
        self.assertEqual(self.incident(), original)
        self.store.db.close()
        self.store = Store(self.path, self.clock)
        self.assertEqual(self.incident(), original)
        self.assertEqual(len(self.rows()), 1)

    def test_hourly_clock_and_coalesced_downtime(self):
        onset = self.clock()
        self.ingest(self.alert(onset=onset))
        self.clock.advance(3599)
        self.store.tick()
        self.assertFalse(
            any(
                r[0] == "reminder"
                for r in self.store.db.execute("SELECT kind FROM events")
            )
        )
        self.clock.advance(1)
        self.store.tick()
        self.assertEqual(
            self.store.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind='reminder'"
            ).fetchone()[0],
            1,
        )
        self.clock.advance(4 * 3600)
        self.store.tick()
        self.assertEqual(
            self.store.db.execute(
                "SELECT COUNT(*) FROM outbox o JOIN events e ON e.seq=o.seq WHERE e.kind='reminder' AND o.state='pending'"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(self.incident()["next_reminder"], onset + 6 * 3600)

    def test_late_cutover_sends_one_initial_then_next_slot(self):
        self.ingest(self.alert(onset=self.clock() - 7400))
        self.store.tick()
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1
        )
        self.assertGreater(self.incident()["next_reminder"], self.clock())
        self.assertLess(self.incident()["next_reminder"], self.clock() + 3600)

    def test_mixed_truncated_payload_resolves_only_explicit_member(self):
        onset = self.clock()
        self.ingest(self.alert(fp="aa", onset=onset), self.alert(fp="bb", onset=onset))
        result = self.ingest(self.alert("resolved", fp="aa", onset=onset), truncated=1)
        self.assertTrue(result["incomplete"])
        states = {i["fingerprint"]: i["state"] for i in self.store.incidents()}
        self.assertEqual(states, {"aa": "recovered", "bb": "firing"})

    def test_old_resolution_and_late_firing_do_not_close_new_episode(self):
        first = self.clock()
        self.ingest(self.alert(onset=first))
        self.ingest(self.alert("resolved", onset=first))
        self.clock.advance(60)
        self.ingest(self.alert(onset=self.clock()))
        self.ingest(self.alert("resolved", onset=first))
        self.ingest(self.alert(onset=first))
        self.assertEqual(
            sorted(i["state"] for i in self.store.incidents()), ["firing", "recovered"]
        )

    def test_schema_failure_is_atomic(self):
        with self.assertRaises(Invalid):
            self.ingest(self.alert(), {"status": "bad"})
        self.assertEqual(self.store.incidents(), [])
        self.assertEqual(self.rows(), [])

    def test_transaction_failure_rolls_back_state_and_outbox(self):
        original = self.store.emit

        def fail(*args):
            original(*args)
            raise sqlite3.OperationalError("synthetic storage fault")

        with patch.object(self.store, "emit", fail), self.assertRaises(sqlite3.Error):
            self.ingest(self.alert())
        self.assertEqual(self.store.incidents(), [])
        self.assertEqual(self.rows(), [])

    def test_ticket_first_ack_is_shared_and_idempotent(self):
        self.subscribe()
        self.ingest(self.alert())
        with self.assertRaises(Invalid):
            self.command()
        self.assertIsNone(self.incident()["ack"])
        ticket = self.evidence()
        item = self.incident()
        args = {
            "incident_id": item["id"],
            "expected_revision": item["revision"],
            "request_id": "ack-1",
            "ticket": ticket,
        }
        first = self.store.command(PRINCIPAL, "ack_incident", args, JIRA)
        self.assertEqual(
            self.store.command(PRINCIPAL, "ack_incident", args, JIRA), first
        )
        self.assertEqual({r["state"] for r in self.rows()}, {"cancelled"})
        with self.assertRaises(Conflict):
            self.store.command(
                PRINCIPAL, "ack_incident", {**args, "request_id": "new"}, JIRA
            )
        with self.assertRaises(Conflict):
            self.store.command(PRINCIPAL, "rearm_incident", args, JIRA)

    def test_wrong_ticket_and_correlation_fail(self):
        self.ingest(self.alert())
        ticket = self.evidence()
        for field, value in [
            ("url", "https://attacker.invalid/OPS-42"),
            ("incident_id", "another"),
            ("comment_id", ""),
            ("verified_at", iso(self.clock() - 1000)),
        ]:
            with self.subTest(field=field), self.assertRaises(Invalid):
                self.command(ticket={**ticket, field: value})
        self.assertIsNone(self.incident()["ack"])

    def test_human_ack_snooze_rearm_and_worsening(self):
        alert = self.alert()
        self.ingest(alert)
        self.command(principal=HUMAN)
        self.ingest({**alert, "labels": {**alert["labels"], "severity": "critical"}})
        self.assertIsNotNone(self.incident()["ack"])
        self.assertEqual(
            self.store.db.execute(
                "SELECT kind FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()[0],
            "worsened",
        )
        self.command("rearm_incident")
        self.assertIsNone(self.incident()["ack"])
        self.command("snooze_incident", until=iso(self.clock() + 7200))
        self.clock.advance(3600)
        self.store.tick()
        self.assertFalse(
            any(
                r[0] == "reminder"
                for r in self.store.db.execute("SELECT kind FROM events")
            )
        )

    def test_recovery_while_acked_is_delivered(self):
        self.subscribe()
        alert = self.alert()
        self.ingest(alert)
        self.command(ticket=self.evidence())
        self.ingest({**alert, "status": "resolved"})
        self.drain()
        deliveries = [
            v for _, v, _, _ in self.transport.calls if v.get("name") == EVENT
        ]
        self.assertEqual([v["data"]["kind"] for v in deliveries], ["recovered"])

    def test_missing_telemetry_unknown_not_recovered(self):
        self.ingest(self.alert())
        self.store.reconcile([], False)
        self.assertEqual(self.incident()["state"], "unknown")
        self.clock.advance(60)
        self.store.reconcile([], True)
        self.assertNotEqual(self.incident()["state"], "recovered")
        self.clock.advance(60)
        self.store.reconcile([], True)
        self.assertEqual(self.incident()["state"], "recovered")

    def test_subscription_challenge_secret_at_rest_and_restart(self):
        sub, _ = self.subscribe()
        self.assertTrue(sub["id"])
        self.assertIsNotNone(sub["refreshBefore"])
        self.assertNotIn(
            SECRET,
            self.store.db.execute("SELECT data FROM subscriptions").fetchone()[0],
        )
        self.store.db.close()
        self.store = Store(self.path, self.clock)
        self.assertEqual(self.store.subscriptions()[0]["id"], sub["id"])
        self.assertTrue(self.store.subscriptions()[0]["active"])

    def test_challenge_failure_bad_secret_filters_and_ttl(self):
        self.transport.challenge_ok = False
        with self.assertRaises(Invalid):
            self.subscribe()
        self.assertEqual(self.store.subscriptions(), [])
        self.transport.challenge_ok = True
        for args in [
            {"arguments": {"cluster": "other"}},
            {"arguments": {"cluster": "bastion", "extra": 1}},
            {"ttlMs": -1},
        ]:
            with self.assertRaises(Invalid):
                self.subscribe(**args)

    def test_standard_webhooks_signature_and_event_envelope(self):
        self.subscribe()
        self.ingest(self.alert())
        self.drain()
        url, value, headers, raw = next(
            c for c in self.transport.calls if c[1].get("name") == EVENT
        )
        verified = Webhook(SECRET).verify(raw, headers)
        self.assertEqual(verified, value)
        self.assertEqual(set(value), {"eventId", "name", "timestamp", "data", "cursor"})
        with self.assertRaises(Exception):
            Webhook(SECRET).verify(raw + b" ", headers)
        self.assertEqual(headers["webhook-id"], value["eventId"])

    def test_signing_timestamp_uses_single_clock_read(self):
        from datetime import datetime, timezone

        with patch.object(self.store, "clock", side_effect=[1000.9, 1001.1]):
            headers = self.events.sign(SECRET, "sub", "event", b"{}")
        self.assertEqual(headers["webhook-timestamp"], "1000")
        self.assertEqual(
            headers["webhook-signature"],
            Webhook(SECRET).sign(
                "event", datetime.fromtimestamp(1000.9, timezone.utc), "{}"
            ),
        )

    def test_channel_failure_isolated_retry_id_stable_and_rotation(self):
        sub, args = self.subscribe()
        self.ingest(self.alert())
        self.transport.status = 503
        self.drain()
        states = {r["dest"]: r["state"] for r in self.rows()}
        self.assertEqual(states["discord"], "accepted")
        self.assertEqual(states[sub["id"]], "pending")
        first = next(c for c in self.transport.calls if c[1].get("name") == EVENT)
        new = "whsec_" + base64.b64encode(b"another-synthetic-key-not-prod12").decode()
        self.events.subscribe(
            PRINCIPAL, {**args, "delivery": {**args["delivery"], "secret": new}}
        )
        self.clock.advance(10)
        self.transport.status = 200
        self.drain()
        last = [c for c in self.transport.calls if c[1].get("name") == EVENT][-1]
        self.assertEqual(first[1]["eventId"], last[1]["eventId"])
        self.assertNotEqual(first[2]["webhook-timestamp"], last[2]["webhook-timestamp"])
        self.assertEqual(len(last[2]["webhook-signature"].split()), 2)

    def test_410_does_not_resurrect_unsubscribe_or_overwrite_refresh(self):
        sub, args = self.subscribe()
        self.ingest(self.alert())
        self.transport.status = 410
        unsub = {
            **args,
            "delivery": {k: v for k, v in args["delivery"].items() if k != "secret"},
        }
        self.transport.on_send = lambda: self.events.unsubscribe(PRINCIPAL, unsub)
        self.events.deliver_one("dot")
        self.assertEqual(self.store.subscriptions(), [])
        self.transport.on_send = None
        sub, args = self.subscribe()
        self.ingest(self.alert(fp="cc"))
        before = self.store.subscriptions()[0]["generation"]
        self.transport.on_send = lambda: self.events.subscribe(PRINCIPAL, args)
        self.events.deliver_one("dot")
        self.assertTrue(self.store.subscriptions()[0]["active"])
        self.assertNotEqual(self.store.subscriptions()[0]["generation"], before)

    def test_ack_during_send_preserves_receipt_and_stops_later_messages(self):
        self.subscribe()
        self.ingest(self.alert())
        self.transport.on_send = lambda: self.command(principal=HUMAN)
        self.events.deliver_one("discord")
        self.transport.on_send = None
        self.drain()
        self.assertEqual({r["state"] for r in self.rows()}, {"accepted", "cancelled"})

    def test_replay_rewind_delivers_stable_ids_and_stale_reminder_cancelled(self):
        sub, args = self.subscribe()
        self.ingest(self.alert())
        self.drain()
        event = [c[1] for c in self.transport.calls if c[1].get("name") == EVENT][0]
        self.events.subscribe(PRINCIPAL, {**args, "cursor": cursor(0)})
        self.drain()
        self.assertEqual(
            [
                c[1]["eventId"]
                for c in self.transport.calls
                if c[1].get("name") == EVENT
            ],
            [event["eventId"], event["eventId"]],
        )
        self.command(principal=HUMAN)
        self.events.subscribe(PRINCIPAL, {**args, "cursor": cursor(0)})
        self.drain()
        self.assertEqual(
            len([c for c in self.transport.calls if c[1].get("name") == EVENT]), 2
        )

    def test_replay_after_restart_does_not_resurrect_superseded_reminders(self):
        sub, args = self.subscribe()
        self.ingest(self.alert())
        self.drain()
        for hour in range(3):
            self.clock.advance(3600)
            self.store.set_meta("health_until", self.clock() + 90)
            self.store.tick()
            if hour == 0:
                self.drain()  # One historical reminder was already accepted.
        latest = self.store.db.execute(
            "SELECT id,seq FROM events WHERE kind='reminder' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self.store.db.close()
        self.store = Store(self.path, self.clock)
        self.events = Events(
            self.store, self.key, self.transport, lambda *_: self.grant, DISCORD
        )
        for delivery in (
            args["delivery"],
            {**args["delivery"], "url": "https://second.example.invalid/callback"},
        ):
            with self.subTest(callback=delivery["url"]):
                result = self.events.subscribe(
                    PRINCIPAL, {**args, "delivery": delivery, "cursor": cursor(0)}
                )
                self.transport.calls.clear()
                self.drain()
                reminders = [
                    c[1]
                    for c in self.transport.calls
                    if c[0] == delivery["url"]
                    and c[1].get("data", {}).get("kind") == "reminder"
                ]
                self.assertEqual([e["eventId"] for e in reminders], [latest["id"]])
                current = next(
                    s for s in self.store.subscriptions() if s["id"] == result["id"]
                )
                self.assertEqual(current["cursor"], latest["seq"])

    def test_pruning_during_callback_reports_truncated(self):
        self.ingest(self.alert())
        original = self.transport.request

        def slow_verify(*args):
            self.clock.advance(8 * 86400)
            self.store.prune()
            return original(*args)

        self.transport.request = slow_verify
        result, _ = self.subscribe(cursor=cursor(0))
        self.assertTrue(result["truncated"])
        self.assertEqual(result["cursor"], cursor(1))

    def test_expiry_revocation_413_and_truncated_journal(self):
        sub, args = self.subscribe(ttlMs=1000)
        self.ingest(self.alert())
        self.clock.advance(2)
        self.events.deliver_one("dot")
        self.assertEqual(
            next(r["state"] for r in self.rows() if r["dest"] == sub["id"]), "blocked"
        )
        self.events.subscribe(PRINCIPAL, args)
        self.grant = False
        self.events.deliver_one("dot")
        self.assertEqual(
            next(r["state"] for r in self.rows() if r["dest"] == sub["id"]), "blocked"
        )
        self.grant = True
        self.events.subscribe(PRINCIPAL, args)
        self.transport.status = 413
        self.events.deliver_one("dot")
        self.assertEqual(
            next(r["state"] for r in self.rows() if r["dest"] == sub["id"]),
            "quarantined",
        )
        self.clock.advance(8 * 86400)
        self.store.tick()
        self.assertGreater(self.store.get_meta("expired_deliveries"), 0)
        result, _ = self.subscribe(cursor=cursor(0))
        self.assertTrue(result["truncated"])

    def test_record_seen_is_not_ack_and_is_idempotent(self):
        self.ingest(self.alert())
        item = self.incident()
        event = self.store.db.execute("SELECT id FROM events").fetchone()[0]
        params = {
            "name": "record_event_seen",
            "arguments": {
                "event_id": event,
                "incident_id": item["id"],
                "expected_revision": item["revision"],
                "request_id": "seen-1",
            },
        }
        first = self.api.rpc(PRINCIPAL, "tools/call", params)
        self.assertFalse(first["structuredContent"]["incident_acknowledged"])
        self.command(principal=HUMAN)
        self.assertEqual(self.api.rpc(PRINCIPAL, "tools/call", params), first)

    def test_sources_invalid_snapshot_emits_unknown_and_does_not_stop_tick(self):
        def fetch(url):
            if "/alerts?" in url:
                return [
                    {"fingerprint": "abcd", "labels": {}, "startsAt": iso(self.clock())}
                ]
            if "/rules" in url:
                return {
                    "status": "success",
                    "data": {
                        "groups": [
                            {
                                "rules": [
                                    {
                                        "lastEvaluation": iso(self.clock()),
                                        "health": "ok",
                                    }
                                ]
                            }
                        ]
                    },
                }
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"value": [self.clock(), "1"]}],
                },
            }

        source = Sources(
            self.store,
            "http://am",
            "http://vm",
            "http://metrics",
            "approved_query",
            fetch,
        )
        self.assertFalse(source.check())
        self.assertEqual(self.incident()["state"], "unknown")
        self.clock.advance(3600)
        self.store.tick()
        self.assertTrue(
            any(
                r[0] == "reminder"
                for r in self.store.db.execute("SELECT kind FROM events")
            )
        )

    def test_silenced_api_alert_stays_firing_then_healthy_absence_recovers(self):
        alert = self.alert()
        raw = {k: v for k, v in alert.items() if k != "status"}
        raw["status"] = {"state": "suppressed"}
        present = [raw]

        def fetch(url):
            if "/alerts?" in url:
                self.assertIn("silenced=true&inhibited=true&unprocessed=true", url)
                return present
            if "/rules" in url:
                return {
                    "status": "success",
                    "data": {
                        "groups": [
                            {
                                "rules": [
                                    {
                                        "lastEvaluation": iso(self.clock()),
                                        "health": "ok",
                                    }
                                ]
                            }
                        ]
                    },
                }
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"value": [self.clock(), "1"]}],
                },
            }

        source = Sources(
            self.store,
            "http://am",
            "http://vm",
            "http://metrics",
            "approved_query",
            fetch,
        )
        self.assertTrue(source.check())
        self.assertEqual(self.incident()["state"], "firing")
        present.clear()
        self.clock.advance(60)
        source.check()
        self.clock.advance(60)
        source.check()
        self.assertEqual(self.incident()["state"], "recovered")

    def test_http_wire_discovery_auth_and_persistence_failure(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.api))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"

        def post(path, value, token):
            return urlopen(
                Request(
                    url + path,
                    data=canonical(value).encode(),
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                ),
                timeout=2,
            )

        try:
            for method in ("server/discover", "events/list", "tools/list"):
                with post(
                    "/mcp", {"jsonrpc": "2.0", "id": 1, "method": method}, "synthetic"
                ) as response:
                    self.assertIn("result", json.load(response))
            with self.assertRaises(HTTPError) as denied:
                post(
                    "/mcp",
                    {"jsonrpc": "2.0", "id": 1, "method": "events/list"},
                    "wrong",
                )
            self.assertEqual(denied.exception.code, 401)
            with patch.object(
                self.store, "ingest", side_effect=sqlite3.OperationalError("synthetic")
            ):
                with self.assertRaises(HTTPError) as failure:
                    post(
                        "/hooks/alertmanager",
                        {"version": "4", "alerts": []},
                        self.api.hook_token,
                    )
                self.assertEqual(failure.exception.code, 503)
            readonly = {**PRINCIPAL, "scopes": {"monitoring:read"}}
            self.ingest(self.alert())
            with self.assertRaises(Denied):
                self.api.rpc(
                    readonly,
                    "tools/call",
                    {
                        "name": "rearm_incident",
                        "arguments": {
                            "incident_id": self.incident()["id"],
                            "expected_revision": 1,
                            "request_id": "r",
                        },
                    },
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_ssrf_private_mixed_answers_and_redirect_not_followed(self):
        transport = PublicHTTPS()
        for url in [
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com:8443",
        ]:
            with self.assertRaises(Invalid):
                transport.request(url, b"{}", {})
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with (
            patch("socket.getaddrinfo", return_value=answers),
            patch("socket.create_connection") as connection,
        ):
            with self.assertRaises(Invalid):
                transport.request("https://public.example", b"{}", {})
            connection.assert_not_called()
        # Transport uses http.client, which returns 3xx rather than following Location.
        self.transport.status = 302
        self.subscribe()
        self.ingest(self.alert())
        self.events.deliver_one("dot")
        self.assertEqual(
            len([c for c in self.transport.calls if c[1].get("name") == EVENT]), 1
        )

    def test_old_completion_preserves_concurrent_replay(self):
        sub, args = self.subscribe()
        self.ingest(self.alert())
        self.transport.on_send = lambda: self.events.subscribe(
            PRINCIPAL, {**args, "cursor": cursor(0)}
        )
        self.events.deliver_one("dot")
        row = next(r for r in self.rows() if r["dest"] == sub["id"])
        self.assertEqual(row["state"], "pending")
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 1
        )
        self.transport.on_send = None
        self.events.deliver_one("dot")
        self.assertEqual(
            next(r for r in self.rows() if r["dest"] == sub["id"])["state"], "accepted"
        )

    def test_capacity_cleanup_commits_before_new_emission(self):
        from incident_adapter.store import Capacity

        with patch("incident_adapter.store.MAX_EVENTS", 1):
            self.ingest(self.alert())
            self.clock.advance(3600)
            with self.assertRaises(Capacity):
                self.store.tick()
            self.clock.advance(8 * 86400)
            # Maintenance still commits even if subsequent emissions fill capacity again.
            try:
                self.store.tick()
            except Capacity:
                pass
            self.assertGreater(self.store.get_meta("journal_floor", 0), 0)
            self.assertGreater(self.store.get_meta("expired_deliveries", 0), 0)

    def test_projected_subscription_backfill_and_emit_limits(self):
        from incident_adapter.store import Capacity

        self.ingest(self.alert())
        with patch("incident_adapter.events.MAX_OUTBOX", 1):
            with self.assertRaises(Capacity):
                self.subscribe()
        self.assertEqual(self.store.subscriptions(), [])
        sub, _ = self.subscribe()
        with patch("incident_adapter.store.MAX_OUTBOX", 3):
            with self.assertRaises(Capacity):
                self.ingest(self.alert(fp="cc"))
        self.assertEqual(len(self.store.incidents()), 1)
        self.assertEqual(len(self.rows()), 2)

    def test_out_of_order_delivery_cursor_cannot_skip_pending_event(self):
        self.subscribe()
        self.ingest(self.alert(fp="aa"))
        self.transport.status = 503
        self.events.deliver_one("dot")
        self.ingest(self.alert(fp="bb"))
        self.transport.status = 200
        self.events.deliver_one("dot")
        last = [c[1] for c in self.transport.calls if c[1].get("name") == EVENT][-1]
        self.assertEqual(last["cursor"], cursor(0))

    def test_callback_dns_wait_is_bounded(self):
        release = threading.Event()
        done = threading.Event()

        def blocked_dns(*args, **kwargs):
            try:
                release.wait(2)
                return []
            finally:
                done.set()

        with (
            patch(
                "incident_adapter.transport.socket.getaddrinfo", side_effect=blocked_dns
            ),
            patch("incident_adapter.transport.socket.create_connection") as connect,
        ):
            try:
                start = time.monotonic()
                with self.assertRaises(TimeoutError):
                    PublicHTTPS(timeout=0.05).request(
                        "https://callback.example.invalid/", b"{}", {}
                    )
                self.assertLess(time.monotonic() - start, 0.5)
                connect.assert_not_called()
            finally:
                release.set()
                self.assertTrue(done.wait(1))

    def test_slow_drip_deadline_allows_next_healthy_subscription(self):
        finished = threading.Event()

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header(
                    "Content-Length", "20" if self.path == "/slow" else "2"
                )
                self.end_headers()
                try:
                    if self.path == "/slow":
                        for _ in range(20):
                            self.wfile.write(b"x")
                            self.wfile.flush()
                            if finished.wait(0.05):
                                break
                    else:
                        self.wfile.write(b"{}")
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Callback)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _, args = self.subscribe()
        self.events.unsubscribe(
            PRINCIPAL,
            {
                **args,
                "delivery": {
                    k: v for k, v in args["delivery"].items() if k != "secret"
                },
            },
        )
        for path in ("slow", "healthy"):
            self.events.subscribe(
                PRINCIPAL,
                {
                    **args,
                    "delivery": {
                        **args["delivery"],
                        "url": "https://callback.example.invalid/" + path,
                    },
                },
            )
        self.ingest(self.alert())
        # Force slow first regardless of the stable subscription ID ordering.
        for sub in self.store.subscriptions():
            if sub["url"].endswith("/slow"):
                self.store.db.execute(
                    "UPDATE outbox SET due=due-1 WHERE dest=?", (sub["id"],)
                )

        class LocalTLS:
            def wrap_socket(self, raw, **kwargs):
                class PlainSocket:
                    def __getattr__(self, name):
                        return getattr(raw, name)

                    def do_handshake(self):
                        pass

                return PlainSocket()

        transport = PublicHTTPS(timeout=0.2)
        self.events.transport = transport
        try:
            with (
                patch(
                    "incident_adapter.transport.socket.getaddrinfo",
                    return_value=[
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            6,
                            "",
                            ("93.184.216.34", 443),
                        )
                    ],
                ),
                patch(
                    "incident_adapter.transport.socket.create_connection",
                    side_effect=lambda *a, **kw: local_connect(kw),
                ),
                patch(
                    "incident_adapter.transport.ssl.create_default_context",
                    return_value=LocalTLS(),
                ),
            ):
                # Use a literal local socket so mocked DNS never reaches a network.
                def local_connect(kw):
                    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    raw.settimeout(kw["timeout"])
                    raw.connect(server.server_address)
                    return raw

                began = time.monotonic()
                self.events.deliver_one("dot")
                elapsed = time.monotonic() - began
                self.assertLess(elapsed, 0.7)
                self.events.deliver_one("dot")
            states = {
                s["url"].rsplit("/", 1)[1]: next(
                    r["state"] for r in self.rows() if r["dest"] == s["id"]
                )
                for s in self.store.subscriptions()
            }
            self.assertEqual(states, {"slow": "pending", "healthy": "accepted"})
        finally:
            finished.set()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_stalled_dot_does_not_hold_store_or_discord_worker(self):
        self.subscribe()
        self.ingest(self.alert())
        entered = threading.Event()
        release = threading.Event()
        original = self.transport.request

        def block(url, body, headers):
            if "receiver." in url:
                entered.set()
                release.wait(2)
            return original(url, body, headers)

        self.transport.request = block
        thread = threading.Thread(target=lambda: self.events.deliver_one("dot"))
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
            self.store.tick()
            self.assertTrue(self.events.deliver_one("discord"))
            self.assertEqual(
                next(r for r in self.rows() if r["dest"] == "discord")["state"],
                "accepted",
            )
        finally:
            release.set()
            thread.join()

    def test_list_incidents_pagination_and_no_label_bulk_dump(self):
        self.ingest(self.alert(fp="aa"), self.alert(fp="bb"))
        first = self.api.rpc(
            PRINCIPAL,
            "tools/call",
            {"name": "list_incidents", "arguments": {"limit": 1}},
        )["structuredContent"]
        self.assertEqual(len(first["incidents"]), 1)
        self.assertTrue(first["next"])
        self.assertNotIn("labels", first["incidents"][0])
        second = self.api.rpc(
            PRINCIPAL,
            "tools/call",
            {
                "name": "list_incidents",
                "arguments": {"limit": 1, "after": first["next"]},
            },
        )["structuredContent"]
        self.assertNotEqual(first["incidents"][0]["id"], second["incidents"][0]["id"])


if __name__ == "__main__":
    unittest.main()
