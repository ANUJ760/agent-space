"""Tests for M07 — Users / Organizations.

Validates:
- Organization and User SQLAlchemy models and repositories
- Mapping of Keycloak subject (sub) to internal User
- Immutable external_subject identity guarantee (not trusting email as identity key)
- Automatic organization bootstrapping on first user login
- GET /api/v1/auth/me profile resolution
- Organization management APIs (create, list, get, conflict handling)
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from app.auth import OIDCClient, set_oidc_client
from app.config import KeycloakSettings, Settings
from app.database import DatabaseManager
from app.main import create_app
from app.models.organization import Organization
from app.repositories.organization_repo import OrganizationRepository
from app.services.user_service import reconcile_user
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey, bytes, bytes]:
    """Generate session-scoped RSA keypair for signing auth tokens."""
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
def oidc_setup(rsa_keys: tuple[Any, Any, bytes, bytes]) -> Iterator[OIDCClient]:
    """Set up OIDCClient with mock keys."""
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


def make_token(
    pem_private: bytes,
    sub: str = "keycloak-sub-123",
    username: str = "alice",
    email: str = "alice@example.com",
    roles: list[str] | None = None,
) -> str:
    """Generate signed JWT token for testing."""
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": "http://localhost:8080/realms/agentspace",
        "aud": "agentspace-backend",
        "azp": "agentspace-backend",
        "exp": 253402300799,  # far future
        "preferred_username": username,
        "email": email,
        "email_verified": True,
        "realm_access": {"roles": roles or ["developer"]},
    }
    return jwt.encode(payload, pem_private, algorithm="RS256", headers={"kid": "key-1"})


@pytest.fixture()
async def test_app(oidc_setup: OIDCClient, tmp_path: Path) -> AsyncIterator[FastAPI]:
    """Create test application with isolated file-based database."""
    db_path = tmp_path / "test_app.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    settings = Settings(
        environment="test",
        debug=True,
        log_format="text",
        database_url=db_url,
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()
    await db.disconnect()

    app = create_app(settings=settings)
    yield app


@pytest.fixture()
def client(test_app: FastAPI) -> Iterator[TestClient]:
    """Create TestClient running inside the app."""
    with TestClient(test_app) as c:
        yield c


# ─── Repositories & Reconciliation Unit Tests ───────────────────────────────


class TestUserAndOrganizationRepositories:
    @pytest.mark.asyncio
    async def test_organization_crud(self) -> None:
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        db = DatabaseManager(settings.database)
        await db.connect()
        await db.create_all()

        async with db.session_factory() as session:
            repo = OrganizationRepository(session)
            org = Organization(name="Acme Inc", slug="acme-inc", description="Acme HQ")
            created = await repo.create(org)
            await session.commit()
            org_id = created.id

        async with db.session_factory() as session:
            repo = OrganizationRepository(session)
            fetched = await repo.get_by_id(org_id)
            assert fetched is not None
            assert fetched.name == "Acme Inc"
            assert fetched.slug == "acme-inc"

            by_slug = await repo.get_by_slug("acme-inc")
            assert by_slug is not None
            assert by_slug.id == org_id

            by_name = await repo.get_by_name("Acme Inc")
            assert by_name is not None
            assert by_name.id == org_id

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_reconcile_user_auto_provisions_and_bootstraps_org(
        self, oidc_setup: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_priv, _ = rsa_keys
        token = make_token(pem_priv, sub="kc-sub-001", username="first_user")
        claims = oidc_setup.verify_token(token)
        auth_user = oidc_setup.claims_to_user(claims)

        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        db = DatabaseManager(settings.database)
        await db.connect()
        await db.create_all()

        async with db.session_factory() as session:
            user = await reconcile_user(session, auth_user)
            await session.commit()

            assert user.external_subject == "kc-sub-001"
            assert user.username == "first_user"
            assert user.role == "ORG_ADMIN"
            assert user.organization is not None
            assert user.organization.name == "Default Organization"

        # Subsequent call returns same user and does not duplicate
        async with db.session_factory() as session:
            user2 = await reconcile_user(session, auth_user)
            assert user2.id == user.id

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_external_subject_is_permanent_identity_not_email(
        self, oidc_setup: OIDCClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        """Verify that two users with the same email but different Keycloak sub are distinct."""
        _, _, pem_priv, _ = rsa_keys
        token1 = make_token(pem_priv, sub="sub-A", username="userA", email="shared@company.com")
        token2 = make_token(pem_priv, sub="sub-B", username="userB", email="shared@company.com")

        auth_user1 = oidc_setup.claims_to_user(oidc_setup.verify_token(token1))
        auth_user2 = oidc_setup.claims_to_user(oidc_setup.verify_token(token2))

        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        db = DatabaseManager(settings.database)
        await db.connect()
        await db.create_all()

        async with db.session_factory() as session:
            u1 = await reconcile_user(session, auth_user1)
            u2 = await reconcile_user(session, auth_user2)
            await session.commit()

            assert u1.id != u2.id
            assert u1.external_subject == "sub-A"
            assert u2.external_subject == "sub-B"

        await db.disconnect()


# ─── API Integration Tests ──────────────────────────────────────────────────


class TestAuthMeEndpoint:
    def test_auth_me_unauthenticated_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp.json()["code"] == "UNAUTHORIZED"

    def test_auth_me_authenticated_returns_profile(
        self, client: TestClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_priv, _ = rsa_keys
        token = make_token(
            pem_priv,
            sub="sub-alice-999",
            username="alice_w",
            email="alice@company.com",
            roles=["developer", "admin"],
        )

        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["external_subject"] == "sub-alice-999"
        assert data["username"] == "alice_w"
        assert data["email"] == "alice@company.com"
        assert data["organization"] is not None
        assert data["organization"]["slug"] == "default-org"
        assert "developer" in data["token_roles"]


class TestOrganizationAPIs:
    def test_create_and_get_organization(
        self, client: TestClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_priv, _ = rsa_keys
        token = make_token(pem_priv)

        # 1. Create Organization
        create_resp = client.post(
            "/api/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Stark Industries",
                "slug": "stark-industries",
                "description": "Advanced technology development",
            },
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        org_data = create_resp.json()
        assert org_data["name"] == "Stark Industries"
        assert org_data["slug"] == "stark-industries"
        org_id = org_data["id"]

        # 2. Get Organization by ID
        get_resp = client.get(
            f"/api/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["id"] == org_id

        # 3. List Organizations
        list_resp = client.get(
            "/api/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == status.HTTP_200_OK
        slugs = [o["slug"] for o in list_resp.json()]
        assert "stark-industries" in slugs

    def test_create_organization_duplicate_slug_conflict(
        self, client: TestClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_priv, _ = rsa_keys
        token = make_token(pem_priv)

        client.post(
            "/api/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Org Alpha", "slug": "org-alpha"},
        )

        duplicate_resp = client.post(
            "/api/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Org Alpha 2", "slug": "org-alpha"},
        )
        assert duplicate_resp.status_code == status.HTTP_409_CONFLICT
        body = duplicate_resp.json()
        assert body["code"] == "ORGANIZATION_SLUG_CONFLICT"

    def test_get_nonexistent_organization_returns_404(
        self, client: TestClient, rsa_keys: tuple[Any, Any, bytes, bytes]
    ) -> None:
        _, _, pem_priv, _ = rsa_keys
        token = make_token(pem_priv)
        random_id = str(uuid.uuid4())

        resp = client.get(
            f"/api/v1/organizations/{random_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json()["code"] == "NOT_FOUND"
