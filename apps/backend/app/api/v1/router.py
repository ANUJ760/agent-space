"""API v1 root router.

Aggregates all v1 sub-routers into a single router that is mounted
under the ``/api/v1`` prefix in ``main.py``.
"""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    health,
    organizations,
    project_members,
    projects,
    tasks,
)

router = APIRouter()

# Health & readiness
router.include_router(health.router, prefix="/health", tags=["health"])

# Authentication & current user
router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# Organizations & tenant management
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])

# Projects & project memberships
router.include_router(projects.router, prefix="/projects", tags=["projects"])
router.include_router(project_members.router, prefix="/projects", tags=["project-members"])

# Agent Registry
router.include_router(agents.router, tags=["agents"])

# Tasks & Lifecycle
router.include_router(tasks.router, tags=["tasks"])
