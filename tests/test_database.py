"""Tests for M03 — PostgreSQL / SQLAlchemy Database Infrastructure.

Validates:
- DatabaseManager connection and lifecycle (connect, disconnect)
- Connection pool configuration
- Handling of database connection failure
- Session transactional scope and rollback on error
- Generic BaseRepository CRUD operations on TestModel
- Model mixins (UUID, Timestamp, Version)
- FastAPI get_db_session dependency
"""

import contextlib
import uuid
from collections.abc import AsyncIterator

import pytest
from app.config import DatabaseSettings
from app.database import (
    DatabaseManager,
    get_db_session,
    set_db_manager,
)
from app.models.test_model import TestModel
from app.repositories import BaseRepository
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


class TestModelRepository(BaseRepository[TestModel]):
    """Concrete repository for testing BaseRepository."""

    __test__ = False
    model_class = TestModel


@pytest.fixture()
async def test_db() -> AsyncIterator[DatabaseManager]:
    """Provide an in-memory SQLite database manager for testing."""
    settings = DatabaseSettings(
        url="sqlite+aiosqlite:///:memory:",
        pool_size=5,
        max_overflow=0,
        echo=False,
    )
    db = DatabaseManager(settings)
    await db.connect()
    await db.create_all()
    set_db_manager(db)

    yield db

    await db.drop_all()
    await db.disconnect()


# ─── Lifecycle & Connectivity ───────────────────────────────────────────────


class TestDatabaseLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self) -> None:
        settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
        db = DatabaseManager(settings)

        # Before connect, accessing engine raises RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.engine

        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.session_factory

        await db.connect()
        assert db.engine is not None
        assert db.session_factory is not None

        # Verify connectivity with SELECT 1
        async with db.engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

        await db.disconnect()

        # After disconnect, accessing engine raises RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.engine

    @pytest.mark.asyncio
    async def test_connection_failure_handled(self) -> None:
        """Verify that connection failure raises and cleans up."""
        # Unreachable port on localhost
        bad_settings = DatabaseSettings(
            url="postgresql+asyncpg://postgres:wrong@127.0.0.1:59999/nonexistent",
            pool_timeout=1,
        )
        db = DatabaseManager(bad_settings)
        with pytest.raises(OSError):
            await db.connect()


# ─── Connection Pooling ─────────────────────────────────────────────────────


class TestConnectionPooling:
    def test_pool_configuration(self) -> None:
        settings = DatabaseSettings(
            url="postgresql+asyncpg://postgres:postgres@localhost:5432/agentspace",
            pool_size=15,
            max_overflow=5,
            pool_timeout=45,
            echo=False,
        )
        db = DatabaseManager(settings)
        assert db._settings.pool_size == 15
        assert db._settings.max_overflow == 5
        assert db._settings.pool_timeout == 45


# ─── Session & Transactions ─────────────────────────────────────────────────


class TestDatabaseSession:
    @pytest.mark.asyncio
    async def test_session_commit(self, test_db: DatabaseManager) -> None:
        async with test_db.session_factory() as session:
            item = TestModel(name="test_item_1", description="desc 1")
            session.add(item)
            await session.commit()
            item_id = item.id

        # Verify persisted in separate session
        async with test_db.session_factory() as session:
            fetched = await session.get(TestModel, item_id)
            assert fetched is not None
            assert fetched.name == "test_item_1"

    @pytest.mark.asyncio
    async def test_session_rollback_on_error(self, test_db: DatabaseManager) -> None:
        try:
            async with test_db.session_factory() as session:
                item = TestModel(name="should_rollback")
                session.add(item)
                await session.flush()
                item_id = item.id
                raise ValueError("Intentional error")
        except ValueError:
            pass

        # Verify item was not persisted
        async with test_db.session_factory() as session:
            fetched = await session.get(TestModel, item_id)
            assert fetched is None


# ─── Generic Repository CRUD & Mixins ────────────────────────────────────────


class TestRepositoryCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, test_db: DatabaseManager) -> None:
        async with test_db.session_factory() as session:
            repo = TestModelRepository(session)
            item = TestModel(name="repo_create", description="testing repo")
            created = await repo.create(item)
            await session.commit()

            assert created.id is not None
            assert isinstance(created.id, uuid.UUID)
            assert created.created_at is not None
            assert created.updated_at is not None
            assert created.version == 1

            fetched = await repo.get_by_id(created.id)
            assert fetched is not None
            assert fetched.name == "repo_create"
            assert fetched.description == "testing repo"

    @pytest.mark.asyncio
    async def test_list_all(self, test_db: DatabaseManager) -> None:
        async with test_db.session_factory() as session:
            repo = TestModelRepository(session)
            await repo.create(TestModel(name="item_A"))
            await repo.create(TestModel(name="item_B"))
            await repo.create(TestModel(name="item_C"))
            await session.commit()

            items = await repo.list_all(limit=10)
            assert len(items) >= 3
            names = [i.name for i in items]
            assert "item_A" in names
            assert "item_B" in names
            assert "item_C" in names

    @pytest.mark.asyncio
    async def test_update_and_delete(self, test_db: DatabaseManager) -> None:
        async with test_db.session_factory() as session:
            repo = TestModelRepository(session)
            item = await repo.create(TestModel(name="before_update"))
            await session.commit()
            item_id = item.id

            # Update
            item.name = "after_update"
            item.version = 2
            await repo.update(item)
            await session.commit()

            updated = await repo.get_by_id(item_id)
            assert updated is not None
            assert updated.name == "after_update"
            assert updated.version == 2

            # Delete
            await repo.delete(updated)
            await session.commit()

            deleted = await repo.get_by_id(item_id)
            assert deleted is None


# ─── FastAPI Dependency ─────────────────────────────────────────────────────


class TestFastAPIDatabaseDependency:
    @pytest.mark.asyncio
    async def test_get_db_session_dependency(self, test_db: DatabaseManager) -> None:
        session_gen = get_db_session()
        session = await anext(session_gen)
        assert isinstance(session, AsyncSession)

        # Run query
        result = await session.execute(select(1))
        assert result.scalar() == 1

        # Complete generator (triggers commit)
        with contextlib.suppress(StopAsyncIteration):
            await anext(session_gen)
