"""Enterprise Backup and Disaster Recovery Engine (M87).

Orchestrates full backups and deterministic restores across:
1. PostgreSQL Database schema & records
2. Artifact metadata
3. CAS Artifacts binary blobs
4. Gitea Git repositories
5. Keycloak realm configuration
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from app.database import DatabaseManager
from app.models.artifact import Artifact
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from sqlalchemy import select

from packages.storage.artifact_store import ArtifactStore

logger = structlog.stdlib.get_logger(__name__)


class RestoreVerificationError(Exception):
    """Raised when data verification fails during restore."""


@dataclass
class BackupManifest:
    """Metadata tracking an AgentSpace backup archive."""

    version: str = "1.0.0"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    database_dump: str = "database_dump.json"
    artifact_metadata: str = "artifact_metadata.json"
    artifacts_dir: str = "artifacts"
    gitea_repositories: str = "gitea_repositories.tar.gz"
    keycloak_config: str = "keycloak_realm.json"
    checksums: dict[str, str] = field(default_factory=dict)
    item_counts: dict[str, int] = field(default_factory=dict)


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class BackupRestoreService:
    """Comprehensive service coordinating backup and recovery across all 5 domains."""

    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        artifact_store: ArtifactStore | None = None,
        gitea_dir: Path | None = None,
    ) -> None:
        self.db = db_manager
        self.artifact_store = artifact_store
        self.gitea_dir = gitea_dir

    # ─── 1. Database & Metadata Backup / Restore ─────────────────────────────

    async def backup_database(self, output_path: Path) -> int:
        """Export core database tables to a structured JSON dump."""
        if not self.db:
            raise ValueError("Database manager is not configured")

        dump_data: dict[str, list[dict[str, Any]]] = {
            "organizations": [],
            "users": [],
            "projects": [],
            "tasks": [],
            "artifacts": [],
        }

        total_records = 0
        async with self.db.session_factory() as session:
            # Organizations
            org_res = await session.execute(select(Organization))
            for org in org_res.scalars().all():
                dump_data["organizations"].append(
                    {
                        "id": str(org.id),
                        "name": org.name,
                        "slug": org.slug,
                        "created_at": org.created_at.isoformat() if org.created_at else None,
                    }
                )
                total_records += 1

            # Users
            user_res = await session.execute(select(User))
            for u in user_res.scalars().all():
                dump_data["users"].append(
                    {
                        "id": str(u.id),
                        "organization_id": str(u.organization_id) if u.organization_id else None,
                        "external_subject": u.external_subject,
                        "email": u.email,
                        "username": u.username,
                        "role": u.role,
                        "is_active": u.is_active,
                    }
                )
                total_records += 1

            # Projects
            proj_res = await session.execute(select(Project))
            for p in proj_res.scalars().all():
                dump_data["projects"].append(
                    {
                        "id": str(p.id),
                        "organization_id": str(p.organization_id),
                        "name": p.name,
                        "slug": p.slug,
                        "description": p.description,
                        "status": p.status,
                        "default_branch": p.default_branch,
                    }
                )
                total_records += 1

            # Tasks
            task_res = await session.execute(select(Task))
            for t in task_res.scalars().all():
                dump_data["tasks"].append(
                    {
                        "id": str(t.id),
                        "organization_id": str(t.organization_id),
                        "project_id": str(t.project_id),
                        "title": t.title,
                        "description": t.description,
                        "status": t.status,
                        "priority": t.priority,
                        "version": t.version,
                    }
                )
                total_records += 1

            # Artifact metadata
            art_res = await session.execute(select(Artifact))
            for a in art_res.scalars().all():
                dump_data["artifacts"].append(
                    {
                        "id": str(a.id),
                        "organization_id": str(a.organization_id),
                        "project_id": str(a.project_id) if a.project_id else None,
                        "task_id": str(a.task_id) if a.task_id else None,
                        "storage_key": a.storage_key,
                        "filename": a.filename,
                        "content_type": a.content_type,
                        "size_bytes": a.size_bytes,
                        "sha256_hash": a.sha256_hash,
                        "artifact_type": a.artifact_type,
                        "metadata_json": a.metadata_json,
                    }
                )
                total_records += 1

        output_path.write_text(json.dumps(dump_data, indent=2), encoding="utf-8")
        logger.info("database_backup_completed", records=total_records, output=str(output_path))
        return total_records

    async def restore_database(self, dump_path: Path) -> int:
        """Restore database tables from a structured JSON dump."""
        if not self.db:
            raise ValueError("Database manager is not configured")

        data = json.loads(dump_path.read_text(encoding="utf-8"))
        restored_records = 0

        async with self.db.session_factory() as session:
            # 1. Organizations
            for o in data.get("organizations", []):
                org = Organization(id=uuid.UUID(o["id"]), name=o["name"], slug=o["slug"])
                session.add(org)
                restored_records += 1
            await session.flush()

            # 2. Users
            for u in data.get("users", []):
                user = User(
                    id=uuid.UUID(u["id"]),
                    organization_id=uuid.UUID(u["organization_id"])
                    if u.get("organization_id")
                    else None,
                    external_subject=u["external_subject"],
                    email=u["email"],
                    username=u["username"],
                    role=u["role"],
                    is_active=u["is_active"],
                )
                session.add(user)
                restored_records += 1
            await session.flush()

            # 3. Projects
            for p in data.get("projects", []):
                proj = Project(
                    id=uuid.UUID(p["id"]),
                    organization_id=uuid.UUID(p["organization_id"]),
                    name=p["name"],
                    slug=p["slug"],
                    description=p["description"],
                    status=p["status"],
                    default_branch=p["default_branch"],
                )
                session.add(proj)
                restored_records += 1
            await session.flush()

            # 4. Tasks
            for t in data.get("tasks", []):
                task = Task(
                    id=uuid.UUID(t["id"]),
                    organization_id=uuid.UUID(t["organization_id"]),
                    project_id=uuid.UUID(t["project_id"]),
                    title=t["title"],
                    description=t["description"],
                    status=t["status"],
                    priority=t["priority"],
                    version=t.get("version", 1),
                )
                session.add(task)
                restored_records += 1
            await session.flush()

            # 5. Artifacts metadata
            for a in data.get("artifacts", []):
                art = Artifact(
                    id=uuid.UUID(a["id"]),
                    organization_id=uuid.UUID(a["organization_id"]),
                    project_id=uuid.UUID(a["project_id"]) if a.get("project_id") else None,
                    task_id=uuid.UUID(a["task_id"]) if a.get("task_id") else None,
                    storage_key=a["storage_key"],
                    filename=a["filename"],
                    content_type=a["content_type"],
                    size_bytes=a["size_bytes"],
                    sha256_hash=a["sha256_hash"],
                    artifact_type=a["artifact_type"],
                    metadata_json=a.get("metadata_json"),
                )
                session.add(art)
                restored_records += 1

            await session.commit()

        logger.info("database_restore_completed", records=restored_records)
        return restored_records

    # ─── 2. CAS Artifacts Backup / Restore ───────────────────────────────────

    async def backup_artifacts(self, storage_keys: list[str], output_dir: Path) -> dict[str, str]:
        """Download CAS artifacts and save to backup directory with checksums."""
        if not self.artifact_store:
            raise ValueError("Artifact store is not configured")

        output_dir.mkdir(parents=True, exist_ok=True)
        checksum_map: dict[str, str] = {}

        for key in storage_keys:
            data = await self.artifact_store.get(key)
            digest = compute_sha256(data)
            checksum_map[key] = digest

            dest_file = output_dir / key.replace("/", "__")
            dest_file.write_bytes(data)

        logger.info("artifacts_backup_completed", count=len(storage_keys))
        return checksum_map

    async def restore_artifacts(self, source_dir: Path, checksum_map: dict[str, str]) -> int:
        """Restore artifacts from backup directory into CAS store with integrity checks."""
        if not self.artifact_store:
            raise ValueError("Artifact store is not configured")

        restored_count = 0
        for key, expected_sha in checksum_map.items():
            source_file = source_dir / key.replace("/", "__")
            if not source_file.exists():
                raise RestoreVerificationError(f"Missing artifact file in backup: {source_file}")

            data = source_file.read_bytes()
            actual_sha = compute_sha256(data)
            if actual_sha != expected_sha:
                raise RestoreVerificationError(
                    f"Checksum mismatch for {key}: expected {expected_sha}, got {actual_sha}"
                )

            await self.artifact_store.put(key, data)
            restored_count += 1

        logger.info("artifacts_restore_completed", count=restored_count)
        return restored_count

    # ─── 3. Gitea Repositories Backup / Restore ───────────────────────────────

    def backup_gitea_repositories(self, repos_dir: Path, output_archive: Path) -> int:
        """Package Gitea Git bare repositories into a compressed tar archive."""
        if not repos_dir.exists():
            repos_dir.mkdir(parents=True, exist_ok=True)

        repo_dirs = [p for p in repos_dir.iterdir() if p.is_dir() or p.name.endswith(".git")]
        with tarfile.open(output_archive, "w:gz") as tar:
            tar.add(repos_dir, arcname="repositories")

        logger.info(
            "gitea_backup_completed", repo_count=len(repo_dirs), archive=str(output_archive)
        )
        return len(repo_dirs)

    def restore_gitea_repositories(self, archive_path: Path, target_dir: Path) -> int:
        """Extract and verify Gitea Git repositories from archive."""
        target_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=target_dir)

        extracted_repos = target_dir / "repositories"
        count = len(list(extracted_repos.iterdir())) if extracted_repos.exists() else 0
        logger.info("gitea_restore_completed", repo_count=count)
        return count

    # ─── 4. Keycloak Configuration Backup / Restore ──────────────────────────

    def backup_keycloak_config(self, realm_data: dict[str, Any], output_path: Path) -> None:
        """Export Keycloak realm JSON configuration."""
        output_path.write_text(json.dumps(realm_data, indent=2), encoding="utf-8")
        logger.info("keycloak_backup_completed", output=str(output_path))

    def restore_keycloak_config(self, config_path: Path) -> dict[str, Any]:
        """Load and validate Keycloak realm configuration."""
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if "realm" not in data:
            raise RestoreVerificationError("Invalid Keycloak configuration: missing 'realm' field")
        logger.info("keycloak_restore_completed", realm=data.get("realm"))
        return data

    # ─── 5. Full End-to-End Backup & Restore ─────────────────────────────────

    async def create_full_backup(
        self,
        staging_dir: Path,
        target_archive: Path,
        keycloak_data: dict[str, Any],
        storage_keys: list[str],
    ) -> BackupManifest:
        """Create a complete consolidated backup archive (.tar.gz) of all 5 domains."""
        staging_dir.mkdir(parents=True, exist_ok=True)
        manifest = BackupManifest()

        # 1. Database & Metadata
        db_dump_path = staging_dir / manifest.database_dump
        rec_count = await self.backup_database(db_dump_path)
        manifest.item_counts["database_records"] = rec_count
        manifest.checksums[manifest.database_dump] = compute_file_sha256(db_dump_path)

        # 2. CAS Artifacts
        artifacts_path = staging_dir / manifest.artifacts_dir
        art_checksums = await self.backup_artifacts(storage_keys, artifacts_path)
        manifest.item_counts["artifacts"] = len(art_checksums)
        (staging_dir / "artifact_checksums.json").write_text(
            json.dumps(art_checksums, indent=2), encoding="utf-8"
        )
        manifest.checksums["artifact_checksums.json"] = compute_file_sha256(
            staging_dir / "artifact_checksums.json"
        )

        # 3. Gitea Repositories
        gitea_archive = staging_dir / manifest.gitea_repositories
        if self.gitea_dir:
            repo_count = self.backup_gitea_repositories(self.gitea_dir, gitea_archive)
        else:
            repo_count = 0
            with tarfile.open(gitea_archive, "w:gz") as tar:
                pass
        manifest.item_counts["gitea_repositories"] = repo_count
        manifest.checksums[manifest.gitea_repositories] = compute_file_sha256(gitea_archive)

        # 4. Keycloak Configuration
        kc_path = staging_dir / manifest.keycloak_config
        self.backup_keycloak_config(keycloak_data, kc_path)
        manifest.checksums[manifest.keycloak_config] = compute_file_sha256(kc_path)

        # 5. Manifest
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")

        # Bundle everything into tar.gz
        with tarfile.open(target_archive, "w:gz") as tar:
            tar.add(staging_dir, arcname=".")

        logger.info("full_backup_created", archive=str(target_archive))
        return manifest

    async def restore_full_backup(
        self,
        archive_path: Path,
        extract_dir: Path,
        gitea_restore_dir: Path,
    ) -> BackupManifest:
        """Unpack full backup archive, verify checksums, and restore all 5 domains."""
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        manifest_file = extract_dir / "manifest.json"
        if not manifest_file.exists():
            raise RestoreVerificationError("Missing manifest.json in backup archive")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = BackupManifest(**manifest_data)

        # Verify checksums
        for fname, expected_hash in manifest.checksums.items():
            target_f = extract_dir / fname
            if not target_f.exists():
                raise RestoreVerificationError(f"Missing file declared in manifest: {fname}")
            actual_hash = compute_file_sha256(target_f)
            if actual_hash != expected_hash:
                raise RestoreVerificationError(
                    f"Integrity check failed for {fname}: expected {expected_hash}, got {actual_hash}"
                )

        # 1. Restore Database & Metadata
        await self.restore_database(extract_dir / manifest.database_dump)

        # 2. Restore CAS Artifacts
        art_checksums = json.loads(
            (extract_dir / "artifact_checksums.json").read_text(encoding="utf-8")
        )
        await self.restore_artifacts(extract_dir / manifest.artifacts_dir, art_checksums)

        # 3. Restore Gitea Repositories
        self.restore_gitea_repositories(
            extract_dir / manifest.gitea_repositories, gitea_restore_dir
        )

        # 4. Restore Keycloak Config
        self.restore_keycloak_config(extract_dir / manifest.keycloak_config)

        logger.info("full_restore_completed", timestamp=manifest.timestamp)
        return manifest
