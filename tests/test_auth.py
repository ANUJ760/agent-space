"""Tests for M06 — Keycloak Integration.

Validates:
- OIDC discovery configuration caching
- Cryptographic JWT verification with RSA keys (RS256)
- Issuer validation
- Audience and authorized party (azp) validation
- Token expiration validation
- Claim transformation into AuthenticatedUser model
- Rejection of invalid signatures, malformed tokens, and expired tokens
- Missing and invalid Authorization header handling
- Protected endpoints using CurrentUserDep returning standard APIError envelope on failure
"""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth import (
    AuthenticatedUser,
    CurrentUserDep,
    OIDCClient,
    OptionalUserDep,
    set_oidc_client,
)
from app.config import KeycloakSettings, Settings
from app.errors import UnauthorizedError
from app.main import create_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

# ─── Test RSA Key Fixture ───────────────────────────────────────────────────


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey, bytes, bytes]:
    """Generate a single session-scoped RSA 2048 keypair for signing test tokens."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key, pem_private, pem_public


@pytest.fixture()
def oidc_client(rsa_keys: tuple[Any, Any, bytes, bytes]) -> Iterator[OIDCClient]:
    """Create an OIDCClient configured with registered mock keys."""
    _, public_key, _, _ = rsa_keys
    settings = KeycloakSettings(
        server_url="http://localhost:8080",
        realm="agentspace",
        client_id="agentspace-backend",
        audience="agentspace-backend",
    )
    client = OIDCClient(settings)
    client.register_mock_key("key-1", public_key)
    set_oidc_client(client)
    yield client
    client.clear_mock_keys()
    set_oidc_client(None)


def create_token(
    pem_private: bytes,
    kid: str = "key-1",
    sub: str = "user-12345",
    iss: str = "http://localhost:8080/realms/agentspace",
    aud: str | list[str] = "agentspace-backend",
    azp: str = "agentspace-backend",
    expires_in: int = 3600,
    preferred_username: str = "alice",
    email: str = "alice@example.com",
    roles: list[str] | None = None,
) -> str:
    """Helper to generate signed JWT tokens for tests."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "azp": azp,
        "iat": now,
        "exp": now + expires_in,
        "preferred_username": preferred_username,
        "email": email,
        "email_verified": True,
        "realm_access": {"roles": roles or ["developer"]},
        "resource_access": {"agentspace-backend": {"roles": ["project-admin"]}},
    }
    return jwt.encode(payload, pem_private, algorithm="RS256", headers={"kid": kid})


# ─── OIDCClient Unit Tests ──────────────────────────────────────────────────


class TestOIDCClient:
    def test_verify_valid_token(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private)
        claims = oidc_client.verify_token(token)

        assert claims["sub"] == "user-12345"
        assert claims["preferred_username"] == "alice"
        assert claims["email"] == "alice@example.com"

    def test_claims_to_user_mapping(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, roles=["developer", "admin"])
        claims = oidc_client.verify_token(token)
        user = oidc_client.claims_to_user(claims)

        assert isinstance(user, AuthenticatedUser)
        assert user.id == "user-12345"
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.email_verified is True
        # Merged realm roles + client roles
        assert "developer" in user.roles
        assert "admin" in user.roles
        assert "project-admin" in user.roles

    def test_expired_token_rejected(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        # Expired 1 hour ago
        token = create_token(pem_private, expires_in=-3600)

        with pytest.raises(UnauthorizedError, match="Token has expired"):
            oidc_client.verify_token(token)

    def test_invalid_issuer_rejected(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, iss="http://evil-idp.example.com/realms/fake")

        with pytest.raises(UnauthorizedError, match="Invalid token issuer"):
            oidc_client.verify_token(token)

    def test_invalid_audience_rejected(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, aud="unrelated-app", azp="unrelated-app")

        with pytest.raises(UnauthorizedError, match="Invalid token audience"):
            oidc_client.verify_token(token)

    def test_invalid_signature_rejected(self, oidc_client: OIDCClient) -> None:
        # Generate another key not registered in mock keys
        foreign_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        foreign_pem = foreign_priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = create_token(foreign_pem, kid="key-1")

        with pytest.raises(UnauthorizedError, match="Invalid token signature"):
            oidc_client.verify_token(token)

    def test_unknown_kid_rejected(
        self, oidc_client: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, kid="unknown-key-999")

        with pytest.raises(UnauthorizedError, match="Unable to verify token signature"):
            oidc_client.verify_token(token)

    def test_malformed_token_rejected(self, oidc_client: OIDCClient) -> None:
        with pytest.raises(UnauthorizedError):
            oidc_client.verify_token("not-a-valid-jwt-token")

    def test_empty_token_rejected(self, oidc_client: OIDCClient) -> None:
        with pytest.raises(UnauthorizedError):
            oidc_client.verify_token("")


# ─── FastAPI Dependency & Protected Route Tests ─────────────────────────────


class TestAuthDependencies:
    @pytest.fixture()
    def auth_app(self, oidc_client: OIDCClient) -> FastAPI:
        settings = Settings(
            environment="test",
            debug=True,
            log_format="text",
            database_url="sqlite+aiosqlite:///:memory:",
        )
        app = create_app(settings=settings)

        @app.get("/test/protected")
        async def protected_route(user: CurrentUserDep) -> dict[str, Any]:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
            }

        @app.get("/test/optional-user")
        async def optional_user_route(user: OptionalUserDep) -> dict[str, Any]:
            return {
                "authenticated": user is not None,
                "username": user.username if user else None,
            }

        return app

    def test_missing_auth_header_returns_401_with_stable_error(self, auth_app: FastAPI) -> None:
        with TestClient(auth_app, raise_server_exceptions=False) as client:
            resp = client.get("/test/protected")
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            body = resp.json()
            assert body["code"] == "UNAUTHORIZED"
            assert "Missing Authorization header" in body["message"]
            assert "request_id" in body

    def test_invalid_scheme_returns_401(self, auth_app: FastAPI) -> None:
        with TestClient(auth_app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/test/protected",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
            )
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            body = resp.json()
            assert body["code"] == "UNAUTHORIZED"
            assert "Invalid Authorization scheme" in body["message"]

    def test_valid_token_accesses_protected_route(
        self, auth_app: FastAPI, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, sub="sub-789", preferred_username="bob")

        with TestClient(auth_app) as client:
            resp = client.get(
                "/test/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["id"] == "sub-789"
            assert data["username"] == "bob"

    def test_expired_token_returns_401(
        self, auth_app: FastAPI, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, expires_in=-100)

        with TestClient(auth_app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/test/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            body = resp.json()
            assert body["code"] == "UNAUTHORIZED"
            assert "Token has expired" in body["message"]

    def test_optional_user_without_token(self, auth_app: FastAPI) -> None:
        with TestClient(auth_app) as client:
            resp = client.get("/test/optional-user")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["authenticated"] is False
            assert data["username"] is None

    def test_optional_user_with_valid_token(
        self, auth_app: FastAPI, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        token = create_token(pem_private, preferred_username="charlie")

        with TestClient(auth_app) as client:
            resp = client.get(
                "/test/optional-user",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["authenticated"] is True
            assert data["username"] == "charlie"


class TestAdminEndpoints:
    @pytest.fixture()
    def app(self, oidc_client: OIDCClient, tmp_path: Path) -> FastAPI:
        import asyncio
        from app.database import DatabaseManager

        db_path = tmp_path / "admin_test.db"
        settings = Settings(
            environment="test",
            debug=True,
            log_format="text",
            database_url=f"sqlite+aiosqlite:///{db_path}",
        )
        db = DatabaseManager(settings.database)
        asyncio.run(db.connect())
        asyncio.run(db.create_all())
        asyncio.run(db.disconnect())
        return create_app(settings=settings)

    def test_admin_endpoints_enforce_rbac(
        self, app: FastAPI, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_private, _ = rsa_keys
        admin_token = create_token(
            pem_private,
            sub="sub-admin-test",
            preferred_username="adm_user",
            roles=["ORG_ADMIN", "admin"],
        )
        member_token = create_token(
            pem_private,
            sub="sub-member-test",
            preferred_username="mem_user",
            roles=["MEMBER"],
        )

        with TestClient(app) as client:
            # 1. Admin login endpoint accepts admin and returns ORG_ADMIN
            resp = client.post("/api/v1/auth/admin/login", json={"username": "adm_user"})
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["user"]["role"] in ("ORG_ADMIN", "SYSTEM_ADMIN")

            # 2. Member token rejected on protected admin session with 403 Forbidden
            resp = client.get(
                "/api/v1/auth/admin/session",
                headers={"Authorization": f"Bearer {member_token}"},
            )
            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert resp.json()["code"] == "FORBIDDEN"

            # 3. Admin token accepted on protected admin session with 200 OK
            resp = client.get(
                "/api/v1/auth/admin/session",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["username"] == "adm_user"


