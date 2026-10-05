import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from incident_adapter.auth import OAuth
from incident_adapter.store import Denied


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.grants = Path(self.tmp.name) / "grants.json"
        self.grants.write_text(
            json.dumps(
                {
                    "subject": {
                        "kind": "agent",
                        "scopes": ["monitoring:read", "monitoring:ack"],
                    }
                }
            )
        )
        # Ephemeral test fixture key, never exported or used outside this process.
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.auth = OAuth(
            "https://issuer.invalid",
            "https://adapter.invalid/mcp",
            "https://issuer.invalid/jwks",
            self.grants,
        )
        self.claims = {
            "sub": "subject",
            "iss": "https://issuer.invalid",
            "aud": "https://adapter.invalid/mcp",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "scope": "monitoring:read monitoring:ack",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, **claims):
        return "Bearer " + jwt.encode(
            {**self.claims, **claims},
            self.key,
            algorithm="RS256",
            headers={"kid": "fixture"},
        )

    def test_signature_issuer_audience_expiry_and_scope(self):
        with patch.object(
            self.auth.keys,
            "get_signing_key_from_jwt",
            return_value=SimpleNamespace(key=self.key.public_key()),
        ):
            self.assertEqual(self.auth.authenticate(self.token())["kind"], "agent")
            for claims in [
                {"iss": "https://other.invalid"},
                {"aud": "other"},
                {"exp": 0},
                {"scope": "monitoring:ack"},
                {"sub": "unknown"},
            ]:
                with self.subTest(claims=claims), self.assertRaises(Denied):
                    self.auth.authenticate(self.token(**claims))
            forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with self.assertRaises(Denied):
                self.auth.authenticate(
                    "Bearer " + jwt.encode(self.claims, forged, algorithm="RS256")
                )

    def test_grant_reload_revokes_subscription_and_write_scope(self):
        self.assertTrue(self.auth.authorized("subject", "monitoring:read"))
        self.grants.write_text("{}")
        self.assertFalse(self.auth.authorized("subject", "monitoring:read"))
        self.grants.write_text("broken")
        self.assertFalse(self.auth.authorized("subject", "monitoring:read"))
