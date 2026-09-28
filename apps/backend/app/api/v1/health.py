"""Health and readiness probe endpoints for Agent Space backend.

Distinguishes:
- Liveness (/api/v1/health/live): verifies that the application process is alive.
- Readiness (/api/v1/health/ready): verifies that essential backing services
  (such as PostgreSQL) are connected and responsive.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.database import get_db_manager

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter()


class LivenessResponse(BaseModel):
    """Response returned by liveness probe."""

    status: str = "ok"
    process: str = "alive"
    version: str


class DependencyCheck(BaseModel):
    """Health check status for an individual dependency."""

    status: Literal["up", "down"]
    latency_ms: float | None = None
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Response returned by readiness probe."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyCheck]
    timestamp: str


async def _check_database() -> DependencyCheck:
    """Probe database connectivity and return status with latency."""
    start = time.monotonic()
    try:
        db = get_db_manager()
        if db._engine is None:
            return DependencyCheck(status="down", error="Database engine not connected")
        async with asyncio.timeout(3.0):
            async with db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyCheck(status="up", latency_ms=latency)
    except Exception as exc:
        logger.warning("database_health_check_failed", error_type=type(exc).__name__)
        return DependencyCheck(status="down", error="Database connection failed")


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness Probe",
    description="Returns HTTP 200 as long as the application process is running and responding.",
)
async def liveness() -> LivenessResponse:
    """Liveness probe — verifies the web application process is active."""
    settings = get_settings()
    return LivenessResponse(
        status="ok",
        process="alive",
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"description": "All required dependencies are usable", "model": ReadinessResponse},
        503: {
            "description": "One or more critical dependencies are degraded",
            "model": ReadinessResponse,
        },
    },
    summary="Readiness Probe",
    description="Probes backing services (PostgreSQL) and returns HTTP 200 if ready or 503 if degraded.",
)
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe — verifies all critical dependencies are usable."""
    db_check = await _check_database()
    checks: dict[str, DependencyCheck] = {
        "database": db_check,
    }

    # If any critical check is down, overall status is not_ready
    is_ready = all(check.status == "up" for check in checks.values())
    overall_status: Literal["ready", "not_ready"] = "ready" if is_ready else "not_ready"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=overall_status,
        checks=checks,
        timestamp=datetime.now(UTC).isoformat(),
    )
