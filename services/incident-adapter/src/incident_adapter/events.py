from .store import MAX_OUTBOX
import base64
import hashlib
import hmac
import json
import random
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from cryptography.fernet import Fernet
from standardwebhooks import Webhook
from .store import EVENT, Invalid, Denied, Capacity, canonical, cursor, sequence, iso
from .transport import destination

DEFINITION = {
    "name": EVENT,
    "description": "Bastion monitoring incident state and reminder updates.",
    "delivery": ["webhook"],
    "inputSchema": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "enum": ["bastion"]}},
        "required": ["cluster"],
        "additionalProperties": False,
    },
    "payloadSchema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "revision": {"type": "integer"},
            "kind": {
                "type": "string",
                "enum": [
                    "opened",
                    "reminder",
                    "worsened",
                    "recovered",
                    "monitoring_unknown",
                ],
            },
            "severity": {"type": "string", "enum": ["warning", "critical"]},
            "summary": {"type": "string"},
            "observed_at": {"type": "string", "format": "date-time"},
            "jira_url": {"type": "string"},
        },
        "required": [
            "incident_id",
            "revision",
            "kind",
            "severity",
            "summary",
            "observed_at",
        ],
        "additionalProperties": False,
    },
}


class Events:
    def __init__(self, store, encryption_key, transport, authorized, discord_url=None):
        self.store = store
        self.cipher = Fernet(encryption_key)
        # Wrong at-rest key must fail startup rather than strand deliveries silently.
        with store.lock:
            for existing in store.subscriptions():
                self.cipher.decrypt(existing["secret"].encode())
        self.transport = transport
        self.authorized = authorized
        self.discord_url = discord_url
        if discord_url:
            target = destination(discord_url)
            if (
                target.hostname != "discord.com"
                or not target.path.startswith("/api/webhooks/")
                or target.query
            ):
                raise Invalid(
                    "Discord destination must be an approved discord.com webhook"
                )
            with store.transaction():
                store.db.execute(
                    "UPDATE outbox SET state='pending',due=? WHERE dest='discord' AND state='blocked'",
                    (store.clock(),),
                )

    def identity(self, principal, params):
        if params.get("name") != EVENT or params.get("arguments") != {
            "cluster": "bastion"
        }:
            raise Invalid("unsupported event or filters")
        delivery = params.get("delivery", {})
        if not isinstance(delivery, dict) or delivery.get("mode") != "webhook":
            raise Invalid("webhook delivery required")
        url = delivery.get("url")
        destination(url)
        sid = hashlib.sha256(
            canonical([principal["id"], url, EVENT, {"cluster": "bastion"}]).encode()
        ).hexdigest()
        return sid, url, delivery

    def sign(self, secret, sid, eid, body, old_secret=None):
        at = datetime.fromtimestamp(self.store.clock(), timezone.utc)
        signature = Webhook(secret).sign(eid, at, body.decode())
        if old_secret:
            signature += " " + Webhook(old_secret).sign(eid, at, body.decode())
        return {
            "Content-Type": "application/json",
            "webhook-id": eid,
            "webhook-timestamp": str(int(at.timestamp())),
            "webhook-signature": signature,
            "X-MCP-Subscription-Id": sid,
        }

    def subscribe(self, principal, params):
        if not self.authorized(principal["id"], "monitoring:read"):
            raise Denied("event access revoked")
        if set(params) - {"name", "arguments", "delivery", "ttlMs", "cursor"}:
            raise Invalid("unknown subscription parameters")
        sid, url, delivery = self.identity(principal, params)
        if set(delivery) - {"mode", "url", "secret"}:
            raise Invalid("unknown delivery parameters")
        secret = delivery.get("secret", "")
        try:
            if (
                not secret.startswith("whsec_")
                or not 24 <= len(base64.b64decode(secret[6:], validate=True)) <= 64
            ):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Invalid("invalid webhook signing secret") from None
        ttl = params.get("ttlMs", 86400000)
        # Nonexpiring requests receive a finite lease. No implicit immortal grants.
        if ttl is None:
            ttl = 86400000
        if type(ttl) is not int or ttl <= 0:
            raise Invalid("positive ttlMs required")
        ttl = min(ttl, 86400000)
        requested = sequence(params.get("cursor"))
        with self.store.lock:
            current = next(
                (s for s in self.store.subscriptions() if s["id"] == sid), None
            )
            latest = self.store.db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM events"
            ).fetchone()[0]
            floor = self.store.get_meta("journal_floor", 0)
            latest = max(latest, floor)
            if requested is not None and requested > latest:
                raise Invalid("cursor is ahead of the journal")
        now = self.store.clock()
        # Bounded cache only for the same principal, URL AND signing key.
        cached = (
            current
            and current.get("verified_until", 0) > now
            and self.cipher.decrypt(current["secret"].encode()).decode() == secret
        )
        if not cached:
            challenge = uuid.uuid4().hex
            body = canonical({"type": "verification", "challenge": challenge}).encode()
            eid = str(uuid.uuid4())
            try:
                status, _, response = self.transport.request(
                    url, body, self.sign(secret, sid, eid, body)
                )
                echoed = json.loads(response).get("challenge", "")
                if (
                    not 200 <= status < 300
                    or not isinstance(echoed, str)
                    or not hmac.compare_digest(echoed, challenge)
                ):
                    raise ValueError()
            except Exception:
                raise Invalid("callback challenge_failed") from None
        with self.store.transaction():
            # Recheck authorization after a slow callback verification.
            if not self.authorized(principal["id"], "monitoring:read"):
                raise Denied("event access revoked")
            current = next(
                (s for s in self.store.subscriptions() if s["id"] == sid), None
            )
            # Retention may advance while the callback challenge is in flight.
            floor = self.store.get_meta("journal_floor", 0)
            now = self.store.clock()
            start = (
                requested
                if requested is not None
                else (current["cursor"] if current else floor)
            )
            truncated = start < floor
            start = max(start, floor)
            if not current and len(self.store.subscriptions()) >= 1000:
                raise Capacity("subscription capacity reached")
            sub = {
                "generation": uuid.uuid4().hex,
                "id": sid,
                "owner": principal["id"],
                "url": url,
                "secret": self.cipher.encrypt(secret.encode()).decode(),
                "expires": now + ttl / 1000,
                "cursor": start,
                "active": True,
                "verified_until": now + 300,
            }
            if (
                current
                and self.cipher.decrypt(current["secret"].encode()).decode() != secret
            ):
                sub["old_secret"] = current["secret"]
                sub["rotate_until"] = now + 300
            elif current and current.get("rotate_until", 0) > now:
                sub.update({k: current[k] for k in ("old_secret", "rotate_until")})
            additions = self.store.db.execute(
                "SELECT COUNT(*) FROM events e WHERE e.seq>? AND NOT EXISTS(SELECT 1 FROM outbox o WHERE o.seq=e.seq AND o.dest=?)",
                (start, sid),
            ).fetchone()[0]
            if (
                self.store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
                + additions
                > MAX_OUTBOX
            ):
                raise Capacity("subscription replay exceeds outbox capacity")
            self.store.save_subscription(sub)
            for row in self.store.db.execute(
                "SELECT seq FROM events WHERE seq>? ORDER BY seq", (start,)
            ).fetchall():
                self.store.db.execute(
                    "INSERT INTO outbox(seq,dest,state,due) VALUES (?,?,'pending',?) ON CONFLICT(seq,dest) DO UPDATE SET state='pending', attempts=0, lease=0, attempt_token=NULL, due=excluded.due",
                    (row[0], sid, now),
                )
            return {
                "id": sid,
                "refreshBefore": iso(sub["expires"]),
                "cursor": cursor(start),
                "truncated": truncated,
            }

    def unsubscribe(self, principal, params):
        sid, _, delivery = self.identity(principal, params)
        if set(delivery) != {"mode", "url"}:
            raise Invalid("unsubscribe delivery accepts mode and url only")
        with self.store.transaction():
            self.store.db.execute("DELETE FROM subscriptions WHERE id=?", (sid,))
            self.store.db.execute(
                "UPDATE outbox SET state='cancelled' WHERE dest=? AND state IN ('pending','leased')",
                (sid,),
            )
        return {}

    def advance(self, sid):
        sub = next((s for s in self.store.subscriptions() if s["id"] == sid), None)
        if sub is None:
            return
        for row in self.store.db.execute(
            "SELECT seq,state FROM outbox WHERE dest=? AND seq>? ORDER BY seq",
            (sid, sub["cursor"]),
        ):
            if row["state"] not in ("accepted", "cancelled"):
                break
            sub["cursor"] = row["seq"]
        self.store.save_subscription(sub)

    def deliver_one(self, channel=None):
        now = self.store.clock()
        with self.store.transaction():
            condition = (
                "AND o.dest='discord'"
                if channel == "discord"
                else ("AND o.dest!='discord'" if channel == "dot" else "")
            )
            row = self.store.db.execute(
                "SELECT o.*,e.body,e.incident,e.kind,e.id AS event_id FROM outbox o JOIN events e ON e.seq=o.seq WHERE ((o.state='pending' AND o.due<=?) OR (o.state='leased' AND o.lease<=?)) "
                + condition
                + " ORDER BY o.due,o.seq,o.dest LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return False
            item = self.store.read(row["incident"])
            ordinary = row["kind"] in ("opened", "reminder")
            # Cursor rewind and new subscriptions can backfill previously
            # coalesced rows. Keep history, but never resend superseded slots.
            superseded = (
                row["kind"] == "reminder"
                and self.store.db.execute(
                    "SELECT 1 FROM events WHERE incident=? AND kind='reminder' AND seq>? LIMIT 1",
                    (row["incident"], row["seq"]),
                ).fetchone()
                is not None
            )
            if (
                superseded
                or ordinary
                and (
                    item["ack"]
                    or item["state"] == "recovered"
                    or item["snooze_until"] > now
                )
            ):
                self.store.db.execute(
                    "UPDATE outbox SET state='cancelled' WHERE seq=? AND dest=?",
                    (row["seq"], row["dest"]),
                )
                self.advance(row["dest"])
                return True
            sub = None
            if row["dest"] == "discord":
                if not self.discord_url:
                    # Missing approved destination is visible, not a fake delivery success.
                    self.store.db.execute(
                        "UPDATE outbox SET state='blocked' WHERE seq=? AND dest=?",
                        (row["seq"], row["dest"]),
                    )
                    return True
                url = self.discord_url
                data = json.loads(row["body"])["data"]
                text = f"{data['kind']}: {data['summary']} [{data['severity']}]\nIncident {item['id']}"
                if item["ack"] and item["ack"].get("jira_url"):
                    text += "\n" + item["ack"]["jira_url"]
                text += "\nUse the incident ID in dot to read or acknowledge it."
                body = canonical(
                    {"content": text[:1900], "allowed_mentions": {"parse": []}}
                ).encode()
                headers = {"Content-Type": "application/json"}
                url += ("&" if "?" in url else "?") + "wait=true"
            else:
                sub = next(
                    (s for s in self.store.subscriptions() if s["id"] == row["dest"]),
                    None,
                )
                if (
                    not sub
                    or not sub["active"]
                    or sub["expires"] <= now
                    or not self.authorized(sub["owner"], "monitoring:read")
                ):
                    self.store.db.execute(
                        "UPDATE outbox SET state='blocked' WHERE seq=? AND dest=?",
                        (row["seq"], row["dest"]),
                    )
                    return True
                url = sub["url"]
                envelope = json.loads(row["body"])
                # Only advertise the contiguous accepted prefix, never the current
                # event's seq when an earlier delivery may still be pending.
                envelope["cursor"] = cursor(sub["cursor"])
                body = canonical(envelope).encode()
                secret = self.cipher.decrypt(sub["secret"].encode()).decode()
                old = (
                    self.cipher.decrypt(sub["old_secret"].encode()).decode()
                    if sub.get("rotate_until", 0) > now
                    else None
                )
                headers = self.sign(secret, sub["id"], row["event_id"], body, old)
            attempt_token = uuid.uuid4().hex
            self.store.db.execute(
                "UPDATE outbox SET state='leased',lease=?,attempt_token=?,attempts=attempts+1 WHERE seq=? AND dest=?",
                (now + 30, attempt_token, row["seq"], row["dest"]),
            )
        # Recheck immediately before network IO. ACK after this check is the documented in-flight race.
        with self.store.lock:
            state = self.store.db.execute(
                "SELECT state FROM outbox WHERE seq=? AND dest=?",
                (row["seq"], row["dest"]),
            ).fetchone()[0]
            if state != "leased":
                return True
            if sub:
                latest = next(
                    (s for s in self.store.subscriptions() if s["id"] == sub["id"]),
                    None,
                )
                if (
                    not latest
                    or not latest["active"]
                    or latest["expires"] <= self.store.clock()
                    or latest.get("generation") != sub.get("generation")
                    or not self.authorized(sub["owner"], "monitoring:read")
                ):
                    with self.store.transaction():
                        self.store.db.execute(
                            "UPDATE outbox SET state='pending',due=? WHERE seq=? AND dest=? AND state='leased'",
                            (self.store.clock(), row["seq"], row["dest"]),
                        )
                    return True
        try:
            status, response_headers, response = self.transport.request(
                url, body, headers
            )
        except Exception:
            status, response_headers, response = 599, {}, b""
        receipt = None
        if 200 <= status < 300 and row["dest"] == "discord":
            try:
                receipt = str(json.loads(response)["id"])
            except Exception:
                status = 599  # Unknown delivery outcome; retry can duplicate, never claim exactly-once.
        with self.store.transaction():
            self.store.db.execute(
                "INSERT INTO receipts VALUES (?,?,?,?,?,?)",
                (
                    attempt_token,
                    row["seq"],
                    row["dest"],
                    self.store.clock(),
                    status,
                    receipt,
                ),
            )
            token_row = self.store.db.execute(
                "SELECT attempt_token FROM outbox WHERE seq=? AND dest=?",
                (row["seq"], row["dest"]),
            ).fetchone()
            if token_row is None or token_row[0] != attempt_token:
                return True  # A refresh/replay owns the newer row; keep the old receipt separately.
            current = self.store.db.execute(
                "SELECT state FROM outbox WHERE seq=? AND dest=?",
                (row["seq"], row["dest"]),
            ).fetchone()[0]
            # Preserve the receipt of an in-flight send even if ACK cancelled its lease.
            if 200 <= status < 300:
                state = "accepted"
            elif status == 410:
                state = "gone"
                if sub:
                    latest = next(
                        (s for s in self.store.subscriptions() if s["id"] == sub["id"]),
                        None,
                    )
                    if latest and latest.get("generation") == sub.get("generation"):
                        latest["active"] = False
                        self.store.save_subscription(latest)
            elif status == 413:
                state = "quarantined"
            elif current == "cancelled":
                state = "cancelled"
            elif row["attempts"] + 1 >= 10 or (
                400 <= status < 500 and status not in (408, 429)
            ):
                state = "exhausted"
            else:
                state = "pending"
            delay = min(900, 2 ** (row["attempts"] + 1) + random.random())
            retry = next(
                (v for k, v in response_headers.items() if k.lower() == "retry-after"),
                None,
            )
            if retry:
                try:
                    retry = float(retry)
                except ValueError:
                    try:
                        retry = (
                            parsedate_to_datetime(retry).timestamp()
                            - self.store.clock()
                        )
                    except (ValueError, TypeError):
                        retry = 0
                delay = max(delay, max(0, retry))
            self.store.db.execute(
                "UPDATE outbox SET state=?,due=?,lease=0,receipt=? WHERE seq=? AND dest=?",
                (state, self.store.clock() + delay, receipt, row["seq"], row["dest"]),
            )
            self.advance(row["dest"])
        return True
