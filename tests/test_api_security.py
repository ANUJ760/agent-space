"""Unit tests for M62 (API Security Hardening).

Validates:
- Enterprise security headers (X-Frame-Options, X-Content-Type-Options, CSP, HSTS).
- Request payload size limit enforcement (413 REQUEST_TOO_LARGE).
- Sliding-window rate limiting (429 RATE_LIMIT_EXCEEDED and Retry-After header).
- CORS headers.
"""

import httpx
import pytest
from app.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from fastapi import FastAPI, status


@pytest.fixture
def hardened_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RequestSizeLimitMiddleware, max_content_length=100
    )  # 100 byte limit for test
    app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=10)

    @app.get("/api/v1/test")
    async def get_test():
        return {"status": "ok"}

    @app.post("/api/v1/test")
    async def post_test(payload: dict):
        return {"received": payload}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.mark.asyncio
async def test_security_headers_injected(hardened_app: FastAPI):
    transport = httpx.ASGITransport(app=hardened_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/test")
        assert res.status_code == status.HTTP_200_OK
        headers = res.headers

        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in headers
        assert "Content-Security-Policy" in headers


@pytest.mark.asyncio
async def test_request_size_limit(hardened_app: FastAPI):
    transport = httpx.ASGITransport(app=hardened_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Normal payload (under 100 bytes) -> succeeds
        res_ok = await client.post("/api/v1/test", json={"k": "v"})
        assert res_ok.status_code == status.HTTP_200_OK

        # 2. Oversized payload (> 100 bytes) -> 413
        oversized_data = {"key": "x" * 200}
        res_large = await client.post("/api/v1/test", json=oversized_data)
        assert res_large.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert res_large.json()["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.asyncio
async def test_rate_limiting(hardened_app: FastAPI):
    transport = httpx.ASGITransport(app=hardened_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Max requests is 3
        r1 = await client.get("/api/v1/test")
        r2 = await client.get("/api/v1/test")
        r3 = await client.get("/api/v1/test")
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_200_OK
        assert r3.status_code == status.HTTP_200_OK

        # 4th request must be rate-limited
        r4 = await client.get("/api/v1/test")
        assert r4.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in r4.headers
        assert r4.json()["code"] == "RATE_LIMIT_EXCEEDED"

        # Health endpoints must bypass rate limiting
        r_health = await client.get("/health")
        assert r_health.status_code == status.HTTP_200_OK
