"""Async SQLAlchemy database engine and session management for Agent Space.

Provides:
- Async engine factory with connection pooling configuration
- Async session factory
- FastAPI dependency for request-scoped database sessions
- Engine lifecycle management (startup/shutdown)
- Base model class for all ORM models

The engine connects to PostgreSQL via asyncpg in production and can use
aiosqlite for testing.
"""

from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import DatabaseSettings

logger = structlog.stdlib.get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    All application models should inherit from this class. Alembic
    migrations will auto-detect models registered against this Base.
    """

    pass


class DatabaseManager:
    """Manages the async database engine and session factory lifecycle.

    Usage:
        db = DatabaseManager(settings.database)
        await db.connect()       # create engine + verify connectivity
        ...
        await db.disconnect()    # dispose engine and connection pool

    Sessions are obtained via:
        async with db.session() as session:
            ...
        # or via the FastAPI dependency ``get_db_session``
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Return the active engine, raising if not connected."""
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory, raising if not connected."""
        if self._session_factory is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory

    async def connect(self) -> None:
        """Create the async engine with connection pooling and verify connectivity."""
        url = self._settings.url
        is_sqlite = url.startswith("sqlite")

        engine_kwargs: dict[str, Any] = {
            "echo": self._settings.echo,
        }

        if not is_sqlite:
            # PostgreSQL connection pool settings
            engine_kwargs.update(
                {
                    "pool_size": self._settings.pool_size,
                    "max_overflow": self._settings.max_overflow,
                    "pool_timeout": self._settings.pool_timeout,
                    "pool_pre_ping": True,
                }
            )

        self._engine = create_async_engine(url, **engine_kwargs)

        # For SQLite, enable WAL mode and foreign keys
        if is_sqlite:

            @event.listens_for(self._engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Verify connectivity
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(
                "database_connected",
                url=_mask_url(url),
                pool_size=self._settings.pool_size if not is_sqlite else "N/A",
            )
        except Exception:
            logger.error("database_connection_failed", url=_mask_url(url))
            raise

    async def disconnect(self) -> None:
        """Dispose the engine and release all pooled connections."""
        if self._engine is not None:
            await self._engine.dispose()
            logger.info("database_disconnected")
            self._engine = None
            self._session_factory = None

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a transactional async session scope.

        Usage:
            async for session in db.session():
                ...
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        """Create all tables from registered models. For testing only."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables from registered models. For testing only."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

# Global database manager instance — initialized during app startup
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Return the global DatabaseManager instance."""
    if _db_manager is None:
        raise RuntimeError("DatabaseManager not initialized. Ensure app startup has completed.")
    return _db_manager


def set_db_manager(manager: DatabaseManager | None) -> None:
    """Set the global DatabaseManager instance (called during app startup)."""
    global _db_manager
    _db_manager = manager


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a request-scoped database session.

    The session is committed on success or rolled back on exception.
    """
    db = get_db_manager()
    async with db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Mask password in database URL for safe logging."""
    # Replace password portion: scheme://user:PASSWORD@host -> scheme://user:***@host
    try:
        if "@" in url and ":" in url.split("@")[0]:
            scheme_user, rest = url.rsplit("@", 1)
            if ":" in scheme_user:
                parts = scheme_user.rsplit(":", 1)
                return f"{parts[0]}:***@{rest}"
    except Exception:
        pass
    return url
