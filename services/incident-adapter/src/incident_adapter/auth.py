import json
from pathlib import Path
from urllib.parse import urlsplit
import jwt
from .store import Denied


class OAuth:
    """JWT resource server; principals and grants are reloaded for revocation."""

    def __init__(self, issuer, audience, jwks_url, grants_file):
        if any(urlsplit(url).scheme != "https" for url in (issuer, audience, jwks_url)):
            raise ValueError("OAuth issuer, audience and JWKS must use HTTPS")
        self.issuer = issuer
        self.audience = audience
        self.grants_file = Path(grants_file)
        self.keys = jwt.PyJWKClient(
            jwks_url, cache_jwk_set=True, lifespan=60, timeout=5
        )

    def grant(self, subject):
        try:
            value = json.loads(self.grants_file.read_text()).get(subject)
            if not isinstance(value, dict) or value.get("kind") not in (
                "human",
                "agent",
            ):
                return None
            if not isinstance(value.get("scopes"), list):
                return None
            return value
        except (OSError, ValueError):
            return None

    def authorized(self, subject, scope):
        grant = self.grant(subject)
        return bool(grant and scope in grant["scopes"])

    def authenticate(self, header):
        try:
            if not header.startswith("Bearer "):
                raise ValueError()
            token = header[7:]
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=15,
            )
            grant = self.grant(claims["sub"])
            if not grant:
                raise ValueError()
            scopes = set(claims.get("scope", "").split()) & set(grant["scopes"])
            if "monitoring:read" not in scopes:
                raise ValueError()
            return {"id": claims["sub"], "kind": grant["kind"], "scopes": scopes}
        except Exception:
            raise Denied("invalid or unauthorized access token") from None
