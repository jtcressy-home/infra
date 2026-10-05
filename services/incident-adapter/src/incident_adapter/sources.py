import json
import urllib.request
from urllib.parse import urlencode, urlsplit
from .store import timestamp, Invalid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Sources:
    """Only operator-configured source URLs, never URLs from webhook/event input."""

    def __init__(
        self, store, alertmanager, evaluator, metrics, health_query, fetch=None
    ):
        if not health_query:
            raise ValueError("an explicit required-telemetry health query is mandatory")
        for url in (alertmanager, evaluator, metrics):
            parsed = urlsplit(url)
            if (
                parsed.scheme not in ("https", "http")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("invalid source URL")
        self.store = store
        self.alertmanager = alertmanager.rstrip("/")
        self.evaluator = evaluator.rstrip("/")
        self.metrics = metrics.rstrip("/")
        self.health_query = health_query
        self.fetch = fetch or self.get

    @staticmethod
    def get(url):
        # Static cluster URLs may be private. TLS checks remain on for HTTPS.
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(url, timeout=10) as response:
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise Invalid("source response too large")
            return json.loads(data)

    def check(self):
        healthy = False
        alerts = []
        try:
            raw = self.fetch(
                self.alertmanager
                + "/api/v2/alerts?active=true&silenced=true&inhibited=true&unprocessed=true"
            )
            if not isinstance(raw, list):
                raise Invalid("invalid alert inventory")
            for alert in raw:
                # API v2 contains active/suppressed/unprocessed status, not webhook firing/resolved.
                alerts.append(
                    {
                        "status": "firing",
                        "fingerprint": alert["fingerprint"],
                        "labels": alert["labels"],
                        "startsAt": alert["startsAt"],
                    }
                )
            rules = self.fetch(self.evaluator + "/api/v1/rules")
            groups = rules["data"]["groups"]
            if rules.get("status") != "success" or not groups:
                raise Invalid("missing evaluator groups")
            for group in groups:
                if not group.get("rules"):
                    raise Invalid("empty evaluator group")
                for rule in group["rules"]:
                    evaluated = timestamp(
                        rule.get("lastEvaluation", group.get("lastEvaluation"))
                    )
                    if (
                        rule.get("lastError")
                        or rule.get("health", "ok") != "ok"
                        or not self.store.clock() - 120
                        <= evaluated
                        <= self.store.clock() + 30
                    ):
                        raise Invalid("evaluation unhealthy or stale")
            query = self.fetch(
                self.metrics
                + "/api/v1/query?"
                + urlencode({"query": self.health_query})
            )
            result = query["data"]["result"]
            # The approved query must produce exactly one vector sample: 1 means all required signals are fresh/healthy.
            if (
                query.get("status") != "success"
                or query["data"].get("resultType") != "vector"
                or len(result) != 1
            ):
                raise Invalid("required telemetry unknown")
            at, value = result[0]["value"]
            self.store.validate_alerts(alerts)
            healthy = (
                float(value) == 1
                and self.store.clock() - 90 <= float(at) <= self.store.clock() + 30
            )
        except Exception:
            healthy = False
            alerts = []
        if not healthy:
            self.store.source_fault()
        self.store.reconcile(alerts, healthy)
        return healthy
