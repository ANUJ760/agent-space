"""Agent Space — FastAPI Application Entry Point.

Creates the FastAPI application instance with:
- Structured logging
- CORS middleware
- Request ID middleware
- Structured exception handlers
- API v1 router
- Lifecycle handlers (startup/shutdown hooks)

No business logic lives here.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import Settings, get_settings
from app.database import DatabaseManager, set_db_manager
from app.errors import register_exception_handlers
from app.logging import setup_logging
from app.middleware import (
    IdempotencyMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle manager.

    Startup: configure database connection pool, log configuration summary.
    Shutdown: dispose database pool, log graceful shutdown.
    Future modules will add Redis, NATS, Temporal connections here.
    """
    settings = getattr(app.state, "settings", None) or get_settings()
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        debug=settings.debug,
    )

    # Database lifecycle
    db = DatabaseManager(settings.database)
    try:
        await db.connect()
        set_db_manager(db)
    except Exception:
        logger.error("database_startup_failed")
        # App can still start — health/ready will report degraded in M05
        # For now we allow startup to continue so non-DB endpoints work

    yield

    # Shutdown
    if db._engine is not None:
        await db.disconnect()
    logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory function to create and configure the FastAPI application.

    Args:
        settings: Optional settings override (useful for testing).
                  If not provided, loads from environment.

    Returns:
        Fully configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    # 1. Configure structured logging
    setup_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    # 2. Create FastAPI instance
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="A modular, self-hostable collaboration platform where humans and autonomous AI agents work together on software projects.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # 3. Register middleware (order matters — outermost first)
    # CORS must be added before RequestID so preflight requests are handled
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Idempotent-Replayed", "Idempotency-Key"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(IdempotencyMiddleware)

    # 4. Register structured exception handlers
    register_exception_handlers(app)

    # 5. Mount API v1 router
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    return app


# Module-level app instance for ``uvicorn app.main:app``
app = create_app()
