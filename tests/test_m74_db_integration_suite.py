"""Tests for M74 — Database Integration Test Suite.

Mandatory validations per M74 specification:
1. Migrations:
   - Full migration upgrade from base to head creates all platform tables.
   - Downgrade from head to base drops tables cleanly.
   - Re-upgrade to head is idempotent and leaves schema fully functional.
2. Transactions:
   - Commit persistence across separate sessions.
   - Rollback on error leaves no partial state.
   - Context manager auto-rollback on uncaught exceptions.
3. Foreign Keys:
   - Insertion with invalid foreign key references raises IntegrityError.
   - Cascade deletion cleans up dependent entities (Organization -> Project -> Task).
4. Locks:
   - Row-level lock acquisition via SELECT ... FOR UPDATE (with_for_update).
   - Optimistic concurrency control (version mismatch rejects stale updates).
5. Constraints:
   - Unique organization slug.
   - Scoped unique project slug per organization.
   - Unique user email.
   - Scoped unique agent slug per organization.
   - Scoped unique task dependency (task_id, depends_on_task_id).
   - NOT NULL constraints on critical model fields.
6. Concurrent Assignment:
   - 20 simultaneous atomic assignment requests on an unassigned task.
   - Exactly 1 worker succeeds and 19 workers receive ConflictError (TASK_ALREADY_ASSIGNED).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import app.models  # noqa: F401 - Register all models
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from app.config import DatabaseSettings
from app.database import DatabaseManager
from app.errors import ConflictError
from app.models.agent import Agent
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.task_dependency import TaskDependency
from app.models.user import User
from app.repositories.task_repo import TaskRepository
from app.services.task_state_machine import TaskStatus
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── 1. Migrations Suite ───────────────────────────────────────────────────


class TestDatabaseMigrations:
    """Validates Alembic migration execution, table verification, and rollback."""

    def test_full_migration_upgrade_downgrade_cycle(self, tmp_path: Path) -> None:
        test_db_path = tmp_path / "m74_migration_test.db"
        alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{test_db_path}")

        sync_url = f"sqlite:///{test_db_path}"

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(sync_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        expected_tables = {
            "organizations",
            "users",
            "projects",
            "project_members",
            "agents",
            "tasks",
            "task_dependencies",
            "idempotency_keys",
            "outbox_events",
        }
        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' missing after upgrade head"

        # Verify columns on tasks table
        task_cols = {col["name"] for col in inspector.get_columns("tasks")}
        assert {"id", "organization_id", "project_id", "title", "status", "priority", "version"}.issubset(task_cols)

        # 2. Downgrade to base
        command.downgrade(alembic_cfg, "base")

        inspector_after_down = inspect(engine)
        tables_after_down = set(inspector_after_down.get_table_names())
        for table in expected_tables:
            assert table not in tables_after_down, f"Table '{table}' should have been dropped on downgrade"

        # 3. Idempotent re-upgrade to head
        command.upgrade(alembic_cfg, "head")
        inspector_reup = inspect(engine)
        tables_reup = set(inspector_reup.get_table_names())
        for table in expected_tables:
            assert table in tables_reup, f"Table '{table}' missing after re-upgrade"

        engine.dispose()


# ─── Database Fixture for Async Tests ──────────────────────────────────────


@pytest_asyncio.fixture()
async def db_manager(tmp_path: Path) -> AsyncIterator[DatabaseManager]:
    """Provides an isolated SQLite database manager with WAL & foreign keys enabled."""
    db_file = tmp_path / "m74_integration.db"
    settings = DatabaseSettings(
        url=f"sqlite+aiosqlite:///{db_file}",
        echo=False,
    )
    db = DatabaseManager(settings)
    await db.connect()
    await db.create_all()

    yield db

    await db.drop_all()
    await db.disconnect()


# ─── 2. Transactions Suite ────────────────────────────────────────────────


class TestDatabaseTransactions:
    """Validates transactional integrity, commit persistence, and rollbacks."""

    @pytest.mark.asyncio
    async def test_commit_persists_across_sessions(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()
        async with db_manager.session_factory() as session1:
            org = Organization(
                id=org_id,
                name="Acme Corp",
                slug=f"acme-{uuid.uuid4().hex[:6]}",
            )
            session1.add(org)
            await session1.commit()

        # Separate read-only session
        async with db_manager.session_factory() as session2:
            result = await session2.execute(select(Organization).where(Organization.id == org_id))
            saved_org = result.scalar_one_or_none()
            assert saved_org is not None
            assert saved_org.name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_explicit_rollback_discards_changes(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()
        async with db_manager.session_factory() as session1:
            org = Organization(
                id=org_id,
                name="Rollback Inc",
                slug=f"rollback-{uuid.uuid4().hex[:6]}",
            )
            session1.add(org)
            await session1.rollback()

        async with db_manager.session_factory() as session2:
            result = await session2.execute(select(Organization).where(Organization.id == org_id))
            assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_session_context_manager_rolls_back_on_exception(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()

        with pytest.raises(RuntimeError, match="Simulated crash"):
            async for session in db_manager.session():
                org = Organization(
                    id=org_id,
                    name="Failed Inc",
                    slug=f"failed-{uuid.uuid4().hex[:6]}",
                )
                session.add(org)
                await session.flush()
                raise RuntimeError("Simulated crash")

        # Verify nothing was persisted
        async with db_manager.session_factory() as session2:
            result = await session2.execute(select(Organization).where(Organization.id == org_id))
            assert result.scalar_one_or_none() is None


# ─── 3. Foreign Keys & Cascade Deletion Suite ─────────────────────────────


class TestDatabaseForeignKeys:
    """Validates foreign key enforcement and cascading deletions."""

    @pytest.mark.asyncio
    async def test_foreign_key_violation_on_insert(self, db_manager: DatabaseManager) -> None:
        """Attempting to insert a project with nonexistent organization_id must fail."""
        nonexistent_org_id = uuid.uuid4()
        async with db_manager.session_factory() as session:
            project = Project(
                id=uuid.uuid4(),
                organization_id=nonexistent_org_id,
                name="Orphan Project",
                slug="orphan-project",
                description="Should fail due to missing org",
            )
            session.add(project)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_cascade_delete_organization_deletes_projects_and_tasks(
        self, db_manager: DatabaseManager
    ) -> None:
        """Deleting an organization must cascade delete its projects and associated tasks."""
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task_id = uuid.uuid4()

        async with db_manager.session_factory() as session:
            org = Organization(id=org_id, name="Cascade Corp", slug=f"cascade-{uuid.uuid4().hex[:6]}")
            session.add(org)
            await session.flush()

            proj = Project(
                id=proj_id,
                organization_id=org_id,
                name="Cascade Project",
                slug="cascade-proj",
            )
            session.add(proj)
            await session.flush()

            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Cascade Task",
                priority="MEDIUM",
                status="TODO",
            )
            session.add(task)
            await session.commit()

        # Now delete organization
        async with db_manager.session_factory() as session:
            result = await session.execute(select(Organization).where(Organization.id == org_id))
            org_to_delete = result.scalar_one()
            await session.delete(org_to_delete)
            await session.commit()

        # Verify Project and Task are also removed
        async with db_manager.session_factory() as session:
            proj_result = await session.execute(select(Project).where(Project.id == proj_id))
            assert proj_result.scalar_one_or_none() is None

            task_result = await session.execute(select(Task).where(Task.id == task_id))
            assert task_result.scalar_one_or_none() is None


# ─── 4. Locks & Optimistic Concurrency Suite ──────────────────────────────


class TestDatabaseLocks:
    """Validates row-level locking (SELECT ... FOR UPDATE) and optimistic concurrency."""

    @pytest.mark.asyncio
    async def test_get_by_id_for_update_executes(self, db_manager: DatabaseManager) -> None:
        """Verify get_by_id_for_update successfully executes a locking query."""
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task_id = uuid.uuid4()

        async with db_manager.session_factory() as session:
            org = Organization(id=org_id, name="Lock Org", slug=f"lock-{uuid.uuid4().hex[:6]}")
            session.add(org)
            proj = Project(id=proj_id, organization_id=org_id, name="Lock Proj", slug="lock-proj")
            session.add(proj)
            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Locked Task",
                status="TODO",
            )
            session.add(task)
            await session.commit()

        async with db_manager.session_factory() as session:
            repo = TaskRepository(session)
            locked_task = await repo.get_by_id_for_update(task_id)
            assert locked_task is not None
            assert locked_task.id == task_id
            assert locked_task.title == "Locked Task"

    @pytest.mark.asyncio
    async def test_optimistic_locking_prevents_stale_update(self, db_manager: DatabaseManager) -> None:
        """Updating a task with a mismatched version raises ConflictError."""
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task_id = uuid.uuid4()

        async with db_manager.session_factory() as session:
            org = Organization(id=org_id, name="Version Org", slug=f"ver-{uuid.uuid4().hex[:6]}")
            session.add(org)
            proj = Project(id=proj_id, organization_id=org_id, name="Version Proj", slug="ver-proj")
            session.add(proj)
            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Versioned Task",
                status="TODO",
                version=1,
            )
            session.add(task)
            await session.commit()

        # Update with stale version
        async with db_manager.session_factory() as session:
            repo = TaskRepository(session)
            task_loaded = await repo.get_by_id(task_id)
            assert task_loaded is not None
            task_loaded.title = "Stale Title"

            with pytest.raises(ConflictError) as exc_info:
                await repo.update_with_optimistic_lock(task_loaded, expected_version=999)
            assert exc_info.value.code == "TASK_VERSION_CONFLICT"


# ─── 5. Constraints Suite ─────────────────────────────────────────────────


class TestDatabaseConstraints:
    """Validates unique constraints, scoped unique indexes, and NOT NULL rules."""

    @pytest.mark.asyncio
    async def test_unique_organization_slug_constraint(self, db_manager: DatabaseManager) -> None:
        slug = f"org-dup-{uuid.uuid4().hex[:6]}"
        async with db_manager.session_factory() as session1:
            session1.add(Organization(id=uuid.uuid4(), name="Org 1", slug=slug))
            await session1.commit()

        async with db_manager.session_factory() as session2:
            session2.add(Organization(id=uuid.uuid4(), name="Org 2", slug=slug))
            with pytest.raises(IntegrityError):
                await session2.commit()

    @pytest.mark.asyncio
    async def test_unique_project_slug_scoped_to_organization(self, db_manager: DatabaseManager) -> None:
        org1_id = uuid.uuid4()
        org2_id = uuid.uuid4()
        shared_slug = "same-slug"

        async with db_manager.session_factory() as session:
            session.add(Organization(id=org1_id, name="Org A", slug=f"a-{uuid.uuid4().hex[:6]}"))
            session.add(Organization(id=org2_id, name="Org B", slug=f"b-{uuid.uuid4().hex[:6]}"))
            await session.flush()

            # Same slug in different orgs must SUCCEED
            proj1 = Project(id=uuid.uuid4(), organization_id=org1_id, name="P1", slug=shared_slug)
            proj2 = Project(id=uuid.uuid4(), organization_id=org2_id, name="P2", slug=shared_slug)
            session.add_all([proj1, proj2])
            await session.commit()

        # Same slug in the same org must FAIL
        async with db_manager.session_factory() as session:
            proj3 = Project(id=uuid.uuid4(), organization_id=org1_id, name="P3", slug=shared_slug)
            session.add(proj3)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_unique_user_external_subject_constraint(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()
        subject = f"sub-kc-{uuid.uuid4().hex[:8]}"

        async with db_manager.session_factory() as session:
            session.add(Organization(id=org_id, name="Org", slug=f"org-{uuid.uuid4().hex[:6]}"))
            await session.flush()
            user1 = User(
                id=uuid.uuid4(),
                organization_id=org_id,
                external_subject=subject,
                email="user1@example.com",
                username="user1",
                display_name="User One",
            )
            session.add(user1)
            await session.commit()

        async with db_manager.session_factory() as session:
            user2 = User(
                id=uuid.uuid4(),
                organization_id=org_id,
                external_subject=subject,
                email="user2@example.com",
                username="user2",
                display_name="User Two",
            )
            session.add(user2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_unique_task_dependency_constraint(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task1_id = uuid.uuid4()
        task2_id = uuid.uuid4()

        async with db_manager.session_factory() as session:
            session.add(Organization(id=org_id, name="Org", slug=f"org-{uuid.uuid4().hex[:6]}"))
            session.add(Project(id=proj_id, organization_id=org_id, name="Proj", slug="proj"))
            await session.flush()

            t1 = Task(id=task1_id, organization_id=org_id, project_id=proj_id, title="Task 1")
            t2 = Task(id=task2_id, organization_id=org_id, project_id=proj_id, title="Task 2")
            session.add_all([t1, t2])
            await session.flush()

            dep1 = TaskDependency(id=uuid.uuid4(), task_id=task1_id, depends_on_task_id=task2_id)
            session.add(dep1)
            await session.commit()

        async with db_manager.session_factory() as session:
            dep2 = TaskDependency(id=uuid.uuid4(), task_id=task1_id, depends_on_task_id=task2_id)
            session.add(dep2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_unique_agent_slug_scoped_to_organization(self, db_manager: DatabaseManager) -> None:
        org_id = uuid.uuid4()
        agent_slug = "test-agent-slug"

        async with db_manager.session_factory() as session:
            session.add(Organization(id=org_id, name="Org", slug=f"org-{uuid.uuid4().hex[:6]}"))
            await session.flush()

            a1 = Agent(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="Agent 1",
                slug=agent_slug,
                role="DEVELOPER",
            )
            session.add(a1)
            await session.commit()

        async with db_manager.session_factory() as session:
            a2 = Agent(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="Agent 2",
                slug=agent_slug,
                role="RESEARCHER",
            )
            session.add(a2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_not_null_constraint_violation(self, db_manager: DatabaseManager) -> None:
        async with db_manager.session_factory() as session:
            # Name cannot be None on Organization
            org = Organization(id=uuid.uuid4(), name=None, slug=f"org-{uuid.uuid4().hex[:6]}")  # type: ignore[arg-type]
            session.add(org)
            with pytest.raises(IntegrityError):
                await session.commit()


# ─── 6. Concurrent Assignment Suite ───────────────────────────────────────


class TestDatabaseConcurrentAssignment:
    """Validates race condition prevention during 20 simultaneous task assignments."""

    @pytest.mark.asyncio
    async def test_20_simultaneous_assignments_yield_1_winner_19_conflicts(
        self, db_manager: DatabaseManager
    ) -> None:
        """When 20 workers concurrently attempt atomic assignment on the same task,

        exactly 1 succeeds and 19 receive TASK_ALREADY_ASSIGNED.
        """
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_ids = [uuid.uuid4() for _ in range(20)]

        # Seed organization, project, agents, and target task
        async with db_manager.session_factory() as session:
            org = Organization(id=org_id, name="Concurrent Org", slug=f"conc-{uuid.uuid4().hex[:6]}")
            session.add(org)
            proj = Project(id=proj_id, organization_id=org_id, name="Concurrent Proj", slug="conc-proj")
            session.add(proj)
            await session.flush()

            for i, aid in enumerate(agent_ids):
                session.add(
                    Agent(
                        id=aid,
                        organization_id=org_id,
                        name=f"Worker {i}",
                        slug=f"worker-{i}-{uuid.uuid4().hex[:4]}",
                        role="CODING",
                        system_prompt="Execute work.",
                    )
                )

            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Highly Contended Task",
                status="TODO",
                version=1,
            )
            session.add(task)
            await session.commit()

        # Concurrent assignment worker function
        async def try_assign(agent_id: uuid.UUID) -> str:
            async with db_manager.session_factory() as session:
                repo = TaskRepository(session)
                try:
                    # Fetch task with lock
                    t = await repo.get_by_id_for_update(task_id)
                    assert t is not None
                    await repo.assign_task_atomic(
                        task=t,
                        assignee_type="AGENT",
                        assignee_id=agent_id,
                        allow_takeover=False,
                    )
                    await session.commit()
                    return "SUCCESS"
                except ConflictError as err:
                    await session.rollback()
                    return f"CONFLICT:{err.code}"

        # Run 20 assignment attempts simultaneously
        results = await asyncio.gather(*(try_assign(aid) for aid in agent_ids))

        successes = [r for r in results if r == "SUCCESS"]
        conflicts = [r for r in results if r.startswith("CONFLICT")]

        assert len(successes) == 1, f"Expected exactly 1 winner, got {len(successes)}"
        assert len(conflicts) == 19, f"Expected exactly 19 conflicts, got {len(conflicts)}"
        assert all(c == "CONFLICT:TASK_ALREADY_ASSIGNED" for c in conflicts)

        # Verify final state in database
        async with db_manager.session_factory() as session:
            repo = TaskRepository(session)
            final_task = await repo.get_by_id(task_id)
            assert final_task is not None
            assert final_task.status == TaskStatus.CLAIMED
            assert final_task.assigned_agent_id in agent_ids
            assert final_task.assigned_user_id is None
            assert final_task.version == 2
