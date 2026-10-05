import hmac
import hashlib
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .auth import OAuth
from .events import Events, DEFINITION
from .sources import Sources
from .store import Store, Invalid, Conflict, Denied, Capacity, canonical
from .transport import PublicHTTPS

VERSION = "2026-07-28"
READ = "monitoring:read"
WRITE = "monitoring:ack"


def schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


S = {"type": "string"}
BASE = {
    "incident_id": S,
    "request_id": S,
    "expected_revision": {"type": "integer", "minimum": 0},
}
TOOLS = [
    {
        "name": "list_incidents",
        "description": "Read current incidents and aggregate delivery faults.",
        "inputSchema": schema(
            {"after": S, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}
        ),
    },
    {
        "name": "read_incident",
        "description": "Read one current incident and destination delivery receipts.",
        "inputSchema": schema({"incident_id": S}, ["incident_id"]),
    },
    {
        "name": "record_event_seen",
        "description": "Record that this caller read an event and current incident. Does not acknowledge the incident.",
        "inputSchema": schema(
            {
                "event_id": S,
                "incident_id": S,
                "expected_revision": {"type": "integer"},
                "request_id": S,
            },
            ["event_id", "incident_id", "expected_revision", "request_id"],
        ),
    },
    {
        "name": "ack_incident",
        "description": "Stop ordinary reminders in both channels after verified OPS ticket read-back. This records caller verification, not independent Jira verification.",
        "inputSchema": schema(
            {
                **BASE,
                "ticket": schema(
                    {
                        "key": S,
                        "url": S,
                        "verified_at": S,
                        "comment_id": S,
                        "incident_id": S,
                    },
                    ["key", "url", "verified_at", "comment_id", "incident_id"],
                ),
            },
            BASE,
        ),
    },
    {
        "name": "snooze_incident",
        "description": "Pause ordinary reminders until the explicit expiry, at most 24 hours.",
        "inputSchema": schema({**BASE, "until": S}, [*BASE, "until"]),
    },
    {
        "name": "rearm_incident",
        "description": "Clear acknowledgment and snooze; resume the incident reminder schedule.",
        "inputSchema": schema(BASE, BASE),
    },
]
for tool in TOOLS:
    tool["annotations"] = {
        "readOnlyHint": tool["name"] in ("list_incidents", "read_incident"),
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


class API:
    def __init__(self, store, events, auth, hook_token, jira_origin, resource):
        if len(hook_token) < 24:
            raise ValueError(
                "webhook token file must contain an approved token of at least 24 characters"
            )
        self.store = store
        self.events = events
        self.auth = auth
        self.hook_token = hook_token
        self.jira_origin = jira_origin
        self.resource = resource

    def rpc(self, principal, method, params):
        if not isinstance(params, dict):
            raise Invalid("object parameters required")
        if method == "server/discover":
            return {
                "resultType": "complete",
                "supportedVersions": [VERSION],
                "capabilities": {"tools": {}, "events": {}},
            }
        if method == "initialize":
            if params.get("protocolVersion") != VERSION:
                raise Invalid("protocol 2026-07-28 required")
            return {
                "protocolVersion": VERSION,
                "capabilities": {"tools": {}, "events": {}},
                "serverInfo": {"name": "incident-adapter", "version": "0.1.0"},
            }
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "events/list":
            return {"events": [DEFINITION]}
        if method == "events/subscribe":
            return self.events.subscribe(principal, params)
        if method == "events/unsubscribe":
            return self.events.unsubscribe(principal, params)
        if method != "tools/call":
            raise Invalid("unknown method")
        name = params.get("name")
        args = params.get("arguments", {})
        definition = next((t for t in TOOLS if t["name"] == name), None)
        if not definition or not isinstance(args, dict):
            raise Invalid("unknown tool or invalid arguments")
        allowed = definition["inputSchema"]["properties"]
        if set(args) - set(allowed) or any(
            k not in args for k in definition["inputSchema"]["required"]
        ):
            raise Invalid("invalid tool arguments")
        if (
            name not in ("list_incidents", "read_incident", "record_event_seen")
            and WRITE not in principal["scopes"]
        ):
            raise Denied("monitoring:ack scope required")
        with self.store.lock:
            if name == "list_incidents":
                limit = args.get("limit", 50)
                after = args.get("after", "")
                if (
                    type(limit) is not int
                    or not 1 <= limit <= 100
                    or not isinstance(after, str)
                ):
                    raise Invalid("invalid pagination")
                rows = self.store.db.execute(
                    "SELECT data FROM incidents WHERE id>? ORDER BY id LIMIT ?",
                    (after, limit + 1),
                ).fetchall()
                items = [json.loads(row[0]) for row in rows]
                result = {
                    "incidents": [
                        {
                            key: item[key]
                            for key in (
                                "id",
                                "revision",
                                "state",
                                "severity",
                                "summary",
                                "onset",
                                "ack",
                            )
                        }
                        for item in items[:limit]
                    ],
                    "next": items[limit - 1]["id"] if len(items) > limit else None,
                    "expired_deliveries": self.store.get_meta("expired_deliveries", 0),
                    "deliveries": [
                        dict(r)
                        for r in self.store.db.execute(
                            "SELECT CASE WHEN dest='discord' THEN 'discord' ELSE 'dot' END AS destination,state,COUNT(*) AS count FROM outbox GROUP BY destination,state"
                        )
                    ],
                }
            elif name == "read_incident":
                item = self.store.read(args["incident_id"])
                result = {
                    "incident": item,
                    "deliveries": [
                        dict(r)
                        for r in self.store.db.execute(
                            "SELECT e.id AS event_id,o.dest,o.state,o.attempts,o.receipt FROM outbox o JOIN events e ON e.seq=o.seq WHERE e.incident=? ORDER BY e.seq DESC LIMIT 100",
                            (item["id"],),
                        )
                    ],
                }
            elif name == "record_event_seen":
                with self.store.transaction():
                    request_id = args["request_id"]
                    if (
                        not isinstance(request_id, str)
                        or not 1 <= len(request_id) <= 128
                    ):
                        raise Invalid("request_id required")
                    digest = hashlib.sha256(
                        canonical([name, args]).encode()
                    ).hexdigest()
                    prior = self.store.db.execute(
                        "SELECT fingerprint,result FROM requests WHERE principal=? AND id=?",
                        (principal["id"], request_id),
                    ).fetchone()
                    if prior:
                        if prior[0] != digest:
                            raise Conflict("request_id already used")
                        result = json.loads(prior[1])
                    else:
                        if (
                            self.store.db.execute(
                                "SELECT COUNT(*) FROM requests"
                            ).fetchone()[0]
                            >= 100000
                        ):
                            raise Capacity("idempotency journal capacity reached")
                        event = self.store.db.execute(
                            "SELECT incident FROM events WHERE id=?",
                            (args["event_id"],),
                        ).fetchone()
                        item = self.store.read(args["incident_id"])
                        if (
                            not event
                            or event[0] != item["id"]
                            or args["expected_revision"] != item["revision"]
                        ):
                            raise Conflict(
                                "read current incident before recording handling"
                            )
                        self.store.db.execute(
                            "INSERT OR IGNORE INTO seen VALUES (?,?,?)",
                            (principal["id"], args["event_id"], self.store.clock()),
                        )
                        result = {
                            "event_id": args["event_id"],
                            "seen": True,
                            "incident_acknowledged": bool(item["ack"]),
                        }
                        self.store.db.execute(
                            "INSERT INTO requests VALUES (?,?,?,?,?)",
                            (
                                principal["id"],
                                request_id,
                                digest,
                                canonical(result),
                                self.store.clock(),
                            ),
                        )
            else:
                result = self.store.command(principal, name, args, self.jira_origin)
        return {
            "content": [{"type": "text", "text": canonical(result)}],
            "structuredContent": result,
            "isError": False,
        }


def handler(api):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log request paths, callbacks, tokens or payloads.

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, status, value, headers=None):
            body = canonical(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                try:
                    with api.store.lock:
                        api.store.db.execute("SELECT 1")
                    self.reply(200, {"status": "ok"})
                except sqlite3.Error:
                    self.reply(503, {"status": "storage_unavailable"})
            elif self.path == "/metrics":
                with api.store.lock:
                    values = [
                        f"incident_adapter_source_healthy {int(api.store.get_meta('health_until', 0) >= api.store.clock())}",
                        f"incident_adapter_expired_deliveries_total {api.store.get_meta('expired_deliveries', 0)}",
                        f"incident_adapter_worker_errors_total {api.store.get_meta('worker_errors', 0)}",
                        f"incident_adapter_database_bytes {api.store.db.execute('PRAGMA page_count').fetchone()[0] * api.store.db.execute('PRAGMA page_size').fetchone()[0]}",
                    ]
                    for row in api.store.db.execute(
                        "SELECT CASE WHEN dest='discord' THEN 'discord' ELSE 'dot' END AS channel,state,COUNT(*) AS n FROM outbox GROUP BY channel,state"
                    ):
                        values.append(
                            'incident_adapter_outbox{channel="'
                            + row["channel"]
                            + '",state="'
                            + row["state"]
                            + '"} '
                            + str(row["n"])
                        )
                body = ("\n".join(values) + "\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/readyz":
                with api.store.lock:
                    ready = api.store.get_meta("health_until", 0) >= api.store.clock()
                self.reply(200 if ready else 503, {"sources_healthy": ready})
            elif self.path == "/.well-known/oauth-protected-resource":
                self.reply(
                    200,
                    {
                        "resource": api.resource,
                        "authorization_servers": [api.auth.issuer],
                        "scopes_supported": [READ, WRITE],
                        "bearer_methods_supported": ["header"],
                    },
                )
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            rid = None
            try:
                if self.path not in ("/mcp", "/hooks/alertmanager"):
                    self.reply(404, {"error": "not_found"})
                    return
                if self.headers.get("Transfer-Encoding"):
                    raise Invalid("chunked input is unsupported")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024 * 1024:
                    self.reply(413, {"error": "body_size"})
                    return
                if self.path == "/hooks/alertmanager":
                    if not hmac.compare_digest(
                        self.headers.get("Authorization", ""),
                        "Bearer " + api.hook_token,
                    ):
                        raise Denied("invalid webhook authorization")
                    principal = None
                else:
                    if self.headers.get("Origin"):
                        raise Denied("browser origins are not enabled")
                    principal = api.auth.authenticate(
                        self.headers.get("Authorization", "")
                    )
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise Invalid("incomplete request")
                value = json.loads(raw)
                if self.path == "/hooks/alertmanager":
                    self.reply(200, api.store.ingest(value))
                    return
                if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
                    raise Invalid("JSON-RPC 2.0 object required")
                rid = value.get("id")
                if value.get("method") == "notifications/initialized":
                    self.reply(202, {})
                    return
                result = api.rpc(
                    principal, value.get("method"), value.get("params", {})
                )
                self.reply(200, {"jsonrpc": "2.0", "id": rid, "result": result})
            except Denied:
                self.reply(
                    401,
                    {"error": "unauthorized"},
                    {
                        "WWW-Authenticate": 'Bearer resource_metadata="'
                        + api.resource.rsplit("/mcp", 1)[0]
                        + '/.well-known/oauth-protected-resource"'
                    },
                )
            except (Invalid, ValueError, TypeError) as error:
                code = (
                    -32015
                    if "callback" in str(error)
                    else (-32009 if isinstance(error, Conflict) else -32602)
                )
                detail = {"code": code, "message": str(error)[:180]}
                if code == -32015:
                    detail["data"] = {"reason": "challenge_failed"}
                self.reply(400, {"jsonrpc": "2.0", "id": rid, "error": detail})
            except (sqlite3.Error, OSError):
                self.reply(503, {"error": "persistence_or_dependency_unavailable"})
            except Exception:
                self.reply(500, {"error": "internal_error"})

    return Handler


def main():
    os.umask(0o077)
    config = json.loads(Path(os.environ["ADAPTER_CONFIG_FILE"]).read_text())

    def secret(key):
        return Path(config[key]).read_text().strip()

    auth = OAuth(
        config["issuer"], config["resource"], config["jwks_url"], config["grants_file"]
    )
    store = Store(config["database"])
    discord = (
        secret("discord_webhook_file") if config.get("discord_webhook_file") else None
    )
    events = Events(
        store,
        secret("encryption_key_file").encode(),
        PublicHTTPS(),
        auth.authorized,
        discord,
    )
    api = API(
        store,
        events,
        auth,
        secret("alertmanager_token_file"),
        config["jira_origin"],
        config["resource"],
    )
    sources = Sources(
        store,
        config["alertmanager_url"],
        config["vmalert_url"],
        config["metrics_url"],
        config["required_telemetry_query"],
    )
    stop = threading.Event()

    def periodic(action, interval):
        while not stop.is_set():
            try:
                action()
            except Exception:
                # No exception payloads in logs. Readiness freshness fails closed.
                try:
                    with store.lock:
                        store.set_meta(
                            "worker_errors", store.get_meta("worker_errors", 0) + 1
                        )
                except Exception:
                    pass
            stop.wait(interval)

    workers = [
        threading.Thread(target=periodic, args=(sources.check, 60), daemon=True),
        threading.Thread(target=periodic, args=(store.tick, 1), daemon=True),
    ]
    for channel in ("discord", "dot"):
        workers.append(
            threading.Thread(
                target=periodic,
                args=(lambda c=channel: events.deliver_one(c), 0.1),
                daemon=True,
            )
        )
    for worker in workers:
        worker.start()
    server = ThreadingHTTPServer(
        (config.get("listen", "0.0.0.0"), config.get("port", 8080)), handler(api)
    )
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        for worker in workers:
            worker.join(timeout=35)
        store.db.close()


if __name__ == "__main__":
    main()
