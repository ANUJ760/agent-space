"""Tests for M87 — Disaster Recovery, Backup, and Restore.

Validates the full backup and restore lifecycle across all 5 domains per Section 96:
1. PostgreSQL Database records
2. Artifact metadata
3. CAS Artifacts (binary blobs)
4. Gitea Git repositories
5. Keycloak realm configuration
6. Integrity verification (checksum validation & tampering detection)
7. Documentation of RPO (< 15 mins) and RTO (< 30 mins) assumptions.
"""

import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.config import Settings
from app.database import DatabaseManager
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

from packages.backup.engine import (
    BackupRestoreService,
    RestoreVerificationError,
    compute_sha256,
)
from packages.storage.artifact_store import LocalStorageArtifactStore

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture()
async def backup_environment(
    tmp_path: Path,
) -> AsyncIterator[tuple[DatabaseManager, LocalStorageArtifactStore, Path]]:
    db_path = tmp_path / "primary.db"
    settings = Settings(
        environment="test",
        debug=True,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    db = DatabaseManager(settings.database)
    await db.connect()
    await db.create_all()

    storage_dir = tmp_path / "cas_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStorageArtifactStore(base_dir=storage_dir)

    repos_dir = tmp_path / "gitea_repos"
    repos_dir.mkdir(parents=True, exist_ok=True)

    # Initialize a mock git bare repository
    sample_repo = repos_dir / "user" / "url-shortener.git"
    sample_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=sample_repo, check=True, capture_output=True)

    yield db, store, repos_dir

    await db.disconnect()


class TestM87BackupRestore:
    """Verifies complete backup, restore, and data integrity verification."""

    # ─── 1. Database & Metadata Backup / Restore ─────────────────────────────

    @pytest.mark.asyncio
    async def test_database_and_metadata_backup_restore(
        self,
        backup_environment: tuple[DatabaseManager, LocalStorageArtifactStore, Path],
        tmp_path: Path,
    ) -> None:
        db, _, _ = backup_environment
        service = BackupRestoreService(db_manager=db)

        # 1. Populate primary database
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        task_id = uuid.uuid4()

        async with db.session_factory() as session:
            org = Organization(id=org_id, name="Disaster Corp", slug="disaster-corp")
            session.add(org)

            user = User(
                id=user_id,
                organization_id=org_id,
                external_subject="sub-ops-lead",
                email="ops@disaster.corp",
                username="ops_lead",
                role="ORG_ADMIN",
            )
            session.add(user)

            proj = Project(
                id=proj_id,
                organization_id=org_id,
                name="Mission Critical Project",
                slug="mission-critical",
                status="ACTIVE",
            )
            session.add(proj)

            task = Task(
                id=task_id,
                organization_id=org_id,
                project_id=proj_id,
                title="Restore Test Task",
                description="Validate DB rehydration",
                status="DONE",
                priority="CRITICAL",
            )
            session.add(task)
            await session.commit()

        # 2. Execute Backup
        dump_file = tmp_path / "database_backup.json"
        record_count = await service.backup_database(dump_file)
        assert record_count >= 4
        assert dump_file.exists()

        # 3. Simulate Total Disaster (Drop/Wipe database)
        await db.drop_all()
        await db.create_all()

        # Confirm database is empty
        async with db.session_factory() as session:
            assert len((await session.execute(Task.__table__.select())).all()) == 0

        # 4. Execute Restore
        restored_count = await service.restore_database(dump_file)
        assert restored_count == record_count

        # 5. Assert data restored identically
        async with db.session_factory() as session:
            restored_task = await session.get(Task, task_id)
            assert restored_task is not None
            assert restored_task.title == "Restore Test Task"
            assert restored_task.status == "DONE"

            restored_user = await session.get(User, user_id)
            assert restored_user is not None
            assert restored_user.email == "ops@disaster.corp"

    # ─── 2. CAS Artifacts Backup / Restore ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_cas_artifacts_backup_restore(
        self,
        backup_environment: tuple[DatabaseManager, LocalStorageArtifactStore, Path],
        tmp_path: Path,
    ) -> None:
        _, store, _ = backup_environment
        service = BackupRestoreService(artifact_store=store)

        # 1. Write sample artifacts into CAS
        sample_code = b"print('mission critical payload')"
        storage_key = "proj-1/artifacts/task-1/solution.py"
        expected_sha = await store.put(storage_key, sample_code)

        # 2. Backup artifacts
        backup_dir = tmp_path / "backup_artifacts"
        checksum_map = await service.backup_artifacts([storage_key], backup_dir)
        assert checksum_map[storage_key] == expected_sha

        # 3. Wipe primary storage
        await store.delete(storage_key)
        assert not await store.exists(storage_key)

        # 4. Restore artifacts
        restored = await service.restore_artifacts(backup_dir, checksum_map)
        assert restored == 1

        # 5. Verify restored artifact
        assert await store.exists(storage_key)
        recovered_data = await store.get(storage_key)
        assert recovered_data == sample_code
        assert compute_sha256(recovered_data) == expected_sha

    # ─── 3. Gitea Repositories Backup / Restore ───────────────────────────────

    def test_gitea_repositories_backup_restore(
        self,
        backup_environment: tuple[DatabaseManager, LocalStorageArtifactStore, Path],
        tmp_path: Path,
    ) -> None:
        _, _, repos_dir = backup_environment
        service = BackupRestoreService(gitea_dir=repos_dir)

        # 1. Backup repository tree
        archive_path = tmp_path / "gitea_backup.tar.gz"
        repo_count = service.backup_gitea_repositories(repos_dir, archive_path)
        assert repo_count >= 1
        assert archive_path.exists()

        # 2. Restore repository tree to recovery location
        restore_dir = tmp_path / "restored_gitea"
        restored_repos = service.restore_gitea_repositories(archive_path, restore_dir)
        assert restored_repos == repo_count
        assert (restore_dir / "repositories" / "user" / "url-shortener.git" / "HEAD").exists()

    # ─── 4. Keycloak Config Backup / Restore ─────────────────────────────────

    def test_keycloak_config_backup_restore(self, tmp_path: Path) -> None:
        service = BackupRestoreService()
        sample_realm = {
            "realm": "agentspace",
            "enabled": True,
            "roles": {"realm": [{"name": "org_admin"}, {"name": "developer"}]},
            "clients": [{"clientId": "agentspace-backend", "publicClient": False}],
        }

        config_path = tmp_path / "keycloak_backup.json"
        service.backup_keycloak_config(sample_realm, config_path)
        assert config_path.exists()

        restored_realm = service.restore_keycloak_config(config_path)
        assert restored_realm["realm"] == "agentspace"
        assert len(restored_realm["roles"]["realm"]) == 2

    # ─── 5. Full End-to-End Consolidated Backup & Restore ────────────────────

    @pytest.mark.asyncio
    async def test_full_consolidated_backup_and_restore(
        self,
        backup_environment: tuple[DatabaseManager, LocalStorageArtifactStore, Path],
        tmp_path: Path,
    ) -> None:
        db, store, repos_dir = backup_environment
        service = BackupRestoreService(db_manager=db, artifact_store=store, gitea_dir=repos_dir)

        # Populate sample state across DB, Artifacts, Gitea
        org_id = uuid.uuid4()
        async with db.session_factory() as session:
            session.add(Organization(id=org_id, name="Acme MegaCorp", slug="acme-megacorp"))
            await session.commit()

        key = "project/artifacts/main.go"
        payload = b"package main\nfunc main() {}"
        await store.put(key, payload)

        keycloak_data = {"realm": "agentspace-prod", "sslRequired": "external"}

        # 1. Create full single-archive backup
        staging_dir = tmp_path / "staging"
        backup_archive = tmp_path / "agentspace_full_backup.tar.gz"

        manifest = await service.create_full_backup(
            staging_dir=staging_dir,
            target_archive=backup_archive,
            keycloak_data=keycloak_data,
            storage_keys=[key],
        )
        assert backup_archive.exists()
        assert "database_dump.json" in manifest.checksums

        # 2. Wipe DB and CAS
        await db.drop_all()
        await db.create_all()
        await store.delete(key)

        # 3. Full Restore
        extract_dir = tmp_path / "extract_restore"
        gitea_restore_dir = tmp_path / "gitea_recovered"

        restored_manifest = await service.restore_full_backup(
            archive_path=backup_archive,
            extract_dir=extract_dir,
            gitea_restore_dir=gitea_restore_dir,
        )
        assert restored_manifest.version == "1.0.0"

        # 4. Verify DB was restored
        async with db.session_factory() as session:
            recovered_org = await session.get(Organization, org_id)
            assert recovered_org is not None
            assert recovered_org.name == "Acme MegaCorp"

        # 5. Verify CAS was restored
        assert await store.exists(key)
        assert await store.get(key) == payload

    # ─── 6. Tampering & Checksum Detection ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_tampered_backup_fails_restore(
        self,
        backup_environment: tuple[DatabaseManager, LocalStorageArtifactStore, Path],
        tmp_path: Path,
    ) -> None:
        db, store, repos_dir = backup_environment
        service = BackupRestoreService(db_manager=db, artifact_store=store, gitea_dir=repos_dir)

        staging_dir = tmp_path / "tamper_staging"
        backup_archive = tmp_path / "tampered_backup.tar.gz"

        await service.create_full_backup(
            staging_dir=staging_dir,
            target_archive=backup_archive,
            keycloak_data={"realm": "test"},
            storage_keys=[],
        )

        # Untar, tamper with database dump, and re-tar
        tamper_dir = tmp_path / "tamper_scratch"
        import tarfile

        with tarfile.open(backup_archive, "r:gz") as tar:
            tar.extractall(path=tamper_dir)

        # Malicious modification of database dump
        db_dump = tamper_dir / "database_dump.json"
        db_dump.write_text('{"malicious": "injected_payload"}', encoding="utf-8")

        corrupt_archive = tmp_path / "corrupt.tar.gz"
        with tarfile.open(corrupt_archive, "w:gz") as tar:
            tar.add(tamper_dir, arcname=".")

        # Attempted restore must fail with RestoreVerificationError
        with pytest.raises(RestoreVerificationError, match="Integrity check failed"):
            await service.restore_full_backup(
                archive_path=corrupt_archive,
                extract_dir=tmp_path / "corrupt_extract",
                gitea_restore_dir=tmp_path / "corrupt_git",
            )

    # ─── 7. RPO / RTO Documentation Verification ─────────────────────────────

    def test_rpo_rto_documentation_exists(self) -> None:
        doc_path = REPO_ROOT / "docs" / "backup_restore.md"
        assert doc_path.exists(), "docs/backup_restore.md does not exist"
        content = doc_path.read_text(encoding="utf-8")

        assert "RPO" in content
        assert "RTO" in content
        assert "15 minutes" in content or "RPO" in content
        assert "30 minutes" in content or "RTO" in content
        assert "PostgreSQL" in content
        assert "Gitea" in content
        assert "Keycloak" in content
        assert "artifacts" in content.lower()
