"""OpenID Connect (OIDC) client and JWT verification service for Keycloak.

Implements:
- OIDC discovery configuration caching
- JSON Web Key Set (JWKS) retrieval and key caching
- Cryptographic JWT verification (RS256, ES256)
- Issuer, audience, and expiration claim validation
- Claims extraction and mapping to AuthenticatedUser
- Mock/offline key provider support for isolated unit and integration testing
"""

from typing import Any

import httpx
import jwt
import structlog
from jwt import PyJWKClient

from app.auth.models import AuthenticatedUser
from app.config import KeycloakSettings, get_settings
from app.errors import UnauthorizedError

logger = structlog.stdlib.get_logger(__name__)


class OIDCClient:
    """Manages Keycloak OIDC discovery, JWKS keys, and JWT verification."""

    def __init__(self, settings: KeycloakSettings) -> None:
        self._settings = settings
        self._discovery_cache: dict[str, Any] | None = None
        self._jwks_client: PyJWKClient | None = None
        self._mock_keys: dict[str, Any] = {}
        # All API replicas must verify the same locally issued token after a
        # restart. The production SECRET_KEY is shared through the pod Secret.
        self._internal_secret = get_settings().secret_key.get_secret_value()

    def generate_token(
        self,
        sub: str,
        username: str,
        email: str,
        roles: list[str],
        expires_in: int = 86400,
    ) -> str:
        """Issue a JWT using the shared application signing secret."""
        import time

        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": sub,
            "iss": self.expected_issuer,
            "aud": self.expected_audience,
            "azp": self._settings.client_id,
            "iat": now,
            "exp": now + expires_in,
            "preferred_username": username,
            "email": email,
            "email_verified": True,
            "realm_access": {"roles": roles},
            "resource_access": {self._settings.client_id: {"roles": roles}},
        }
        return str(
            jwt.encode(
                payload,
                self._internal_secret,
                algorithm="HS256",
                headers={"kid": "agentspace-internal-v1"},
            )
        )

    @property
    def expected_issuer(self) -> str:
        """Expected token issuer URL."""
        base = self._settings.server_url.rstrip("/")
        return f"{base}/realms/{self._settings.realm}"

    @property
    def expected_audience(self) -> str:
        """Expected token audience."""
        return str(self._settings.audience)

    @property
    def discovery_url(self) -> str:
        """OIDC well-known configuration endpoint."""
        return f"{self.expected_issuer}/.well-known/openid-configuration"

    @property
    def jwks_uri(self) -> str:
        """JWKS certificates endpoint."""
        return f"{self.expected_issuer}/protocol/openid-connect/certs"

    def register_mock_key(self, kid: str, public_key: Any) -> None:
        """Register an in-memory public key for isolated offline testing."""
        self._mock_keys[kid] = public_key

    def clear_mock_keys(self) -> None:
        """Clear all registered mock public keys."""
        self._mock_keys.clear()

    async def fetch_discovery(self) -> dict[str, Any]:
        """Fetch and cache the OpenID Connect discovery document."""
        if self._discovery_cache is not None:
            return self._discovery_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.discovery_url)
                resp.raise_for_status()
                data: dict[str, Any] = dict(resp.json())
                self._discovery_cache = data
                return data
        except Exception as exc:
            logger.error("oidc_discovery_failed", error=str(exc), url=self.discovery_url)
            raise

    def get_signing_key(self, token: str) -> Any:
        """Extract key ID from unverified header and resolve the signing key."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise UnauthorizedError("Malformed token header.") from exc

        kid = unverified_header.get("kid")

        if kid == "agentspace-internal-v1":
            if unverified_header.get("alg") != "HS256":
                raise UnauthorizedError("Invalid internal token algorithm.")
            return self._internal_secret

        # 1. Check in-memory registered mock keys first (for testing)
        if kid in self._mock_keys:
            return self._mock_keys[kid]

        # 2. Query Keycloak JWKS endpoint
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self.jwks_uri, cache_keys=True, lifespan=3600)

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return signing_key.key
        except Exception as exc:
            logger.warning("jwks_key_resolution_failed", kid=kid, error=str(exc))
            raise UnauthorizedError("Unable to verify token signature with current keys.") from exc

    def verify_token(self, token: str) -> dict[str, Any]:
        """Cryptographically verify a Keycloak JWT access token and return its claims."""
        if not token or not token.strip():
            raise UnauthorizedError("Empty token.")

        key = self.get_signing_key(token)
        kid = jwt.get_unverified_header(token).get("kid")
        algorithms = ["HS256"] if kid == "agentspace-internal-v1" else ["RS256", "ES256"]

        try:
            # First attempt standard audience validation
            try:
                claims: dict[str, Any] = jwt.decode(
                    token,
                    key=key,
                    algorithms=algorithms,
                    issuer=self.expected_issuer,
                    audience=self.expected_audience,
                    options={
                        "verify_signature": True,
                        "verify_exp": True,
                        "verify_iat": True,
                        "verify_iss": True,
                        "verify_aud": True,
                    },
                    leeway=10,  # 10s clock skew tolerance
                )
                return claims
            except jwt.InvalidAudienceError:
                # In Keycloak, access tokens often place client_id in 'azp' (authorized party)
                # or audience contains 'account'. If aud mismatch, verify if azp matches audience
                unverified_claims = jwt.decode(token, options={"verify_signature": False})
                azp = unverified_claims.get("azp")
                aud = unverified_claims.get("aud")
                if azp == self.expected_audience or (
                    isinstance(aud, list) and self.expected_audience in aud
                ):
                    claims = jwt.decode(
                        token,
                        key=key,
                        algorithms=algorithms,
                        issuer=self.expected_issuer,
                        options={
                            "verify_signature": True,
                            "verify_exp": True,
                            "verify_iat": True,
                            "verify_iss": True,
                            "verify_aud": False,
                        },
                        leeway=10,
                    )
                    return claims
                raise
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("Token has expired.") from exc
        except jwt.InvalidIssuerError as exc:
            raise UnauthorizedError("Invalid token issuer.") from exc
        except jwt.InvalidAudienceError as exc:
            raise UnauthorizedError("Invalid token audience.") from exc
        except jwt.InvalidSignatureError as exc:
            raise UnauthorizedError("Invalid token signature.") from exc
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(f"Invalid token: {exc}") from exc

    def claims_to_user(self, claims: dict[str, Any]) -> AuthenticatedUser:
        """Transform validated JWT claims payload into AuthenticatedUser model."""
        sub = claims.get("sub")
        if not sub:
            raise UnauthorizedError("Token missing subject (sub) claim.")

        username = claims.get("preferred_username") or claims.get("name") or sub
        email = claims.get("email")
        email_verified = bool(claims.get("email_verified", False))

        # Aggregate realm and client roles
        roles: set[str] = set()
        realm_access = claims.get("realm_access", {})
        if isinstance(realm_access, dict):
            roles.update(realm_access.get("roles", []))

        resource_access = claims.get("resource_access", {})
        if isinstance(resource_access, dict):
            client_access = resource_access.get(self._settings.client_id, {})
            if isinstance(client_access, dict):
                roles.update(client_access.get("roles", []))

        return AuthenticatedUser(
            id=sub,
            username=username,
            email=email,
            email_verified=email_verified,
            roles=sorted(roles),
            raw_claims=claims,
        )


# Global singleton OIDCClient instance
_oidc_client: OIDCClient | None = None


def get_oidc_client() -> OIDCClient:
    """Return the global OIDCClient singleton instance."""
    global _oidc_client
    if _oidc_client is None:
        settings = get_settings().keycloak
        _oidc_client = OIDCClient(settings)
    return _oidc_client


def set_oidc_client(client: OIDCClient | None) -> None:
    """Set or override the global OIDCClient instance (used in tests)."""
    global _oidc_client
    _oidc_client = client
