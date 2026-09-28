"""Tests for M02 — Backend Main / FastAPI Application.

Validates the FastAPI app factory, middleware, error handling, health endpoints,
OpenAPI schema, and CORS configuration using httpx TestClient.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from app.config import Settings
from app.errors import AppException, NotFoundError
from app.main import create_app
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


@pytest.fixture()
def app() -> FastAPI:
    """Create a test application instance."""
    settings = Settings(
        environment="test",
        debug=True,
        log_format="text",
        cors_origins=["http://localhost:3000"],
    )
    return create_app(settings=settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    """Create a test client for the application."""
    with TestClient(app) as c:
        yield c


# ─── Health Endpoints ────────────────────────────────────────────────────────


class TestHealthEndpoints:
    def test_liveness_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_readiness_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ─── Request ID Middleware ───────────────────────────────────────────────────


class TestRequestIDMiddleware:
    def test_response_contains_x_request_id_header(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health/live")
        request_id = resp.headers.get("X-Request-ID")
        assert request_id is not None
        # Should be a valid UUID4
        uuid.UUID(request_id, version=4)

    def test_client_provided_request_id_is_echoed(self, client: TestClient) -> None:
        custom_id = "test-request-123"
        resp = client.get(
            "/api/v1/health/live",
            headers={"X-Request-ID": custom_id},
        )
        assert resp.headers.get("X-Request-ID") == custom_id


# ─── CORS Middleware ─────────────────────────────────────────────────────────


class TestCORSMiddleware:
    def test_cors_headers_present_for_allowed_origin(self, client: TestClient) -> None:
        resp = client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_exposes_request_id_header(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
            },
        )
        exposed = resp.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in exposed


# ─── OpenAPI ─────────────────────────────────────────────────────────────────


class TestOpenAPI:
    def test_openapi_json_loads(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert schema["info"]["title"] == "Agent Space"

    def test_docs_loads(self, client: TestClient) -> None:
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_loads(self, client: TestClient) -> None:
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_health_endpoints_in_openapi(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/health/live" in paths
        assert "/api/v1/health/ready" in paths


# ─── Exception Handlers ─────────────────────────────────────────────────────


class TestExceptionHandlers:
    def test_app_exception_returns_structured_error(self, app: FastAPI) -> None:
        @app.get("/test/app-error")
        async def raise_app_error() -> None:
            raise AppException(
                code="TEST_ERROR",
                message="This is a test error.",
                status_code=status.HTTP_418_IM_A_TEAPOT,
                details={"test": True},
            )

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/test/app-error")
            assert resp.status_code == 418
            body = resp.json()
            assert body["code"] == "TEST_ERROR"
            assert body["message"] == "This is a test error."
            assert body["details"]["test"] is True
            assert "request_id" in body
            # Must NOT contain stack trace
            assert "traceback" not in body
            assert "Traceback" not in resp.text

    def test_not_found_error_returns_404(self, app: FastAPI) -> None:
        @app.get("/test/not-found")
        async def raise_not_found() -> None:
            raise NotFoundError(resource="Task", resource_id="abc-123")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/test/not-found")
            assert resp.status_code == 404
            body = resp.json()
            assert body["code"] == "NOT_FOUND"
            assert "Task" in body["message"]

    def test_validation_error_returns_422(self, app: FastAPI) -> None:
        from pydantic import BaseModel

        class TestBody(BaseModel):
            name: str
            age: int

        @app.post("/test/validate")
        async def validate_body(body: TestBody) -> dict[str, Any]:
            return body.model_dump()

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/test/validate",
                json={"name": 123},  # missing age, wrong type for name
            )
            assert resp.status_code == 422
            body = resp.json()
            assert body["code"] == "VALIDATION_ERROR"
            assert "request_id" in body
            assert "errors" in body["details"]

    def test_unhandled_exception_returns_500_without_trace(self, app: FastAPI) -> None:
        @app.get("/test/crash")
        async def raise_unhandled() -> None:
            raise RuntimeError("Something unexpected broke")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/test/crash")
            assert resp.status_code == 500
            body = resp.json()
            assert body["code"] == "INTERNAL_ERROR"
            assert "request_id" in body
            # Must NOT leak the actual error message
            assert "Something unexpected broke" not in body["message"]
            assert "RuntimeError" not in body["message"]
            assert "Traceback" not in resp.text


# ─── Application Factory ────────────────────────────────────────────────────


class TestAppFactory:
    def test_create_app_returns_fastapi_instance(self) -> None:
        settings = Settings(environment="test", debug=True, log_format="text")
        app = create_app(settings=settings)
        assert app.title == "Agent Space"
        assert app.version == "0.1.0"

    def test_create_app_uses_default_settings_when_none(self) -> None:
        app = create_app()
        assert app.title == "Agent Space"
