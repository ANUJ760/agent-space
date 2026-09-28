"""Minimal health endpoint stubs for M02.

These provide a basic liveness probe so ``uvicorn app.main:app`` can be
verified immediately. Full health and readiness checks (database, Redis,
NATS connectivity) will be implemented in M05.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns OK if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[str, str]:
    """Readiness probe — stub until M05 adds dependency checks."""
    return {"status": "ok"}
