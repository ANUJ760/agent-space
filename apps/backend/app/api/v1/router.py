"""API v1 root router.

Aggregates all v1 sub-routers into a single router that is mounted
under the ``/api/v1`` prefix in ``main.py``.

Health routes are included here as a minimal placeholder until M05
provides full readiness probes.
"""

from fastapi import APIRouter

from app.api.v1 import health

router = APIRouter()

# Health & readiness (minimal M02 stub — will be expanded in M05)
router.include_router(health.router, prefix="/health", tags=["health"])
