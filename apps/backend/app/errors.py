"""Stable API error models and exception handlers for Agent Space backend.

Provides a structured error response format that never exposes internal
stack traces or implementation details. All API errors carry a machine-readable
code, a human-readable message, optional details, and the request ID for
tracing.
"""

import uuid
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = structlog.stdlib.get_logger(__name__)


class APIError(BaseModel):
    """Standardized error response body returned by all API endpoints."""

    code: str
    message: str
    details: dict[str, Any] = {}
    request_id: str = ""


class AppException(Exception):
    """Base application exception that maps to a structured API error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "id": resource_id},
        )


class ConflictError(AppException):
    """Conflict — e.g. optimistic version mismatch or duplicate."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ForbiddenError(AppException):
    """Authorization denied."""

    def __init__(self, message: str = "Access denied.") -> None:
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class UnauthorizedError(AppException):
    """Authentication required or invalid."""

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


def _get_request_id(request: Request) -> str:
    """Extract the request ID from request state, falling back to a new UUID."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.warning(
            "app_exception",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=APIError(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.warning(
            "validation_error",
            errors=str(exc.errors()),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=APIError(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details={"errors": exc.errors()},
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_msg=str(exc),
            request_id=request_id,
        )
        # Never expose internal details in production
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIError(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                request_id=request_id,
            ).model_dump(),
        )
