"""FastAPI dependency injection functions for Agent Space backend.

Provides request-scoped and application-scoped dependencies that are
injected via FastAPI's ``Depends()`` mechanism.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings


def get_request_id(request: Request) -> str:
    """Extract the request ID set by RequestIDMiddleware."""
    return getattr(request.state, "request_id", "unknown")


# Type alias for injecting settings throughout the application
SettingsDep = Annotated[Settings, Depends(get_settings)]
RequestIDDep = Annotated[str, Depends(get_request_id)]
