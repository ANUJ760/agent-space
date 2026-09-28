"""API v1 root router.

Aggregates all v1 sub-routers into a single router that is mounted
under the ``/api/v1`` prefix in ``main.py``.
"""

from fastapi import APIRouter

from app.api.v1 import auth, health, organizations

router = APIRouter()

# Health & readiness
router.include_router(health.router, prefix="/health", tags=["health"])

# Authentication & current user
router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# Organizations & tenant management
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
