"""Tests for M04 — Alembic Migration Infrastructure.

Validates:
- alembic.ini configuration file
- Model metadata registration for autogenerate
- Clean database migration execution (upgrade to head)
- Migration rollback (downgrade to base)
- Version history verification
"""

from pathlib import Path

import app.models  # noqa: F401
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.database import Base
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def alembic_cfg(tmp_path: Path) -> Config:
    """Create an Alembic Config pointing to an isolated SQLite test database."""
    test_db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite+aiosqlite:///{test_db_path}"

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_alembic_ini_exists_and_configured() -> None:
    ini_path = REPO_ROOT / "alembic.ini"
    assert ini_path.is_file(), "alembic.ini missing at repository root"
    cfg = Config(str(ini_path))
    assert cfg.get_main_option("script_location") == "migrations"


def test_model_metadata_registered() -> None:
    # Ensure Base.metadata contains the test model table
    assert "test_items" in Base.metadata.tables


def test_script_directory_loads_history(alembic_cfg: Config) -> None:
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script_dir.walk_revisions())
    assert len(revisions) >= 1, "At least one migration revision must exist"
    head = script_dir.get_current_head()
    assert head is not None
    assert head == revisions[0].revision


def test_clean_migration_upgrade_and_downgrade(alembic_cfg: Config, tmp_path: Path) -> None:
    test_db_path = tmp_path / "test_migration.db"
    sync_url = f"sqlite:///{test_db_path}"

    # 1. Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Inspect created tables using sync engine
    engine = create_engine(sync_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "alembic_version" in tables
    assert "test_items" in tables

    # Verify columns on test_items
    columns = {col["name"]: col for col in inspector.get_columns("test_items")}
    assert "id" in columns
    assert "name" in columns
    assert "description" in columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert "version" in columns

    # 2. Run downgrade to base
    command.downgrade(alembic_cfg, "base")

    # Verify table dropped after downgrade
    inspector = inspect(engine)
    tables_after = inspector.get_table_names()
    assert "test_items" not in tables_after

    engine.dispose()
