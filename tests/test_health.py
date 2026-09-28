"""Tests for M05 — Health / Readiness / Error Handling.

Validates:
- GET /api/v1/health/live (liveness: process is alive)
- GET /api/v1/health/ready (readiness: backing services are connected)
- Degraded state (503 Service Unavailable) when database is down
- Stable API error envelope on standard HTTP errors (404, 405)
- Stable API error envelope on custom application errors (400, 503)
- Verification that no internal exception traces or sensitive data leak to clients
"""

from collections.abc import Iterator

import pytest
from app.config import Settings
from app.database import DatabaseManager, set_db_manager
from app.errors import BadRequestError, ServiceUnavailableError
from app.main import create_app
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


@pytest.fixture()
def healthy_app() -> FastAPI:
    """Create a FastAPI app with working in-memory SQLite database."""
    settings = Settings(
        environment="test",
        debug=True,
        log_format="text",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    return create_app(settings=settings)


@pytest.fixture()
def healthy_client(healthy_app: FastAPI) -> Iterator[TestClient]:
    """TestClient running inside the app lifespan."""
    with TestClient(healthy_app) as client:
        yield client


# ─── Liveness Probe ─────────────────────────────────────────────────────────


class TestLivenessProbe:
    def test_liveness_returns_ok_and_process_alive(self, healthy_client: TestClient) -> None:
        resp = healthy_client.get("/api/v1/health/live")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"
        assert data["process"] == "alive"
        assert "version" in data

    def test_liveness_has_request_id(self, healthy_client: TestClient) -> None:
        resp = healthy_client.get("/api/v1/health/live")
        assert "X-Request-ID" in resp.headers


# ─── Readiness Probe ────────────────────────────────────────────────────────


class TestReadinessProbe:
    def test_readiness_healthy_database_returns_200(self, healthy_client: TestClient) -> None:
        resp = healthy_client.get("/api/v1/health/ready")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ready"
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "up"
        assert isinstance(data["checks"]["database"]["latency_ms"], float)
        assert data["checks"]["database"]["latency_ms"] >= 0.0
        assert "timestamp" in data

    def test_readiness_database_down_returns_503(self) -> None:
        """When database is disconnected, readiness must return HTTP 503."""
        settings = Settings(
            environment="test",
            debug=True,
            log_format="text",
            # Invalid port to simulate database outage
            database_url="postgresql+asyncpg://postgres:wrong@127.0.0.1:59999/down",
        )
        app = create_app(settings=settings)

        # Force a database manager with no engine connected
        disconnected_db = DatabaseManager(settings.database)
        set_db_manager(disconnected_db)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["checks"]["database"]["status"] == "down"
            assert data["checks"]["database"]["error"] is not None
            # Zero leak of internal password or traceback
            assert "wrong" not in resp.text
            assert "Traceback" not in resp.text


# ─── Stable API Error Envelope ───────────────────────────────────────────────


class TestStableAPIErrorFormat:
    def test_unmatched_route_returns_stable_404_error(self, healthy_client: TestClient) -> None:
        resp = healthy_client.get("/api/v1/nonexistent-endpoint")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert "message" in body
        assert "request_id" in body
        assert isinstance(body["details"], dict)

    def test_method_not_allowed_returns_stable_405_error(self, healthy_client: TestClient) -> None:
        resp = healthy_client.post("/api/v1/health/live")
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        body = resp.json()
        assert body["code"] == "METHOD_NOT_ALLOWED"
        assert "request_id" in body

    def test_bad_request_error_envelope(self, healthy_app: FastAPI) -> None:
        @healthy_app.get("/test/bad-request")
        async def bad_request_endpoint() -> None:
            raise BadRequestError(
                message="Invalid filter parameter.",
                details={"param": "status"},
            )

        with TestClient(healthy_app, raise_server_exceptions=False) as client:
            resp = client.get("/test/bad-request")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST
            body = resp.json()
            assert body["code"] == "BAD_REQUEST"
            assert body["message"] == "Invalid filter parameter."
            assert body["details"] == {"param": "status"}
            assert "request_id" in body

    def test_service_unavailable_error_envelope(self, healthy_app: FastAPI) -> None:
        @healthy_app.get("/test/service-unavailable")
        async def service_unavailable_endpoint() -> None:
            raise ServiceUnavailableError(
                message="Temporal cluster unreachable.",
                details={"service": "temporal"},
            )

        with TestClient(healthy_app, raise_server_exceptions=False) as client:
            resp = client.get("/test/service-unavailable")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            body = resp.json()
            assert body["code"] == "SERVICE_UNAVAILABLE"
            assert body["message"] == "Temporal cluster unreachable."
            assert body["details"] == {"service": "temporal"}
            assert "request_id" in body

    def test_internal_error_does_not_leak_stack_trace(self, healthy_app: FastAPI) -> None:
        @healthy_app.get("/test/crash-internal")
        async def crash_endpoint() -> None:
            raise ZeroDivisionError("division by zero in secret calculation")

        with TestClient(healthy_app, raise_server_exceptions=False) as client:
            resp = client.get("/test/crash-internal")
            assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            body = resp.json()
            assert body["code"] == "INTERNAL_ERROR"
            assert body["message"] == "An unexpected error occurred."
            assert "request_id" in body
            # Must NOT contain internal error strings or traceback
            assert "division by zero" not in resp.text
            assert "ZeroDivisionError" not in resp.text
            assert "Traceback" not in resp.text
