"""Unit tests for artifact storage backends and ORM metadata."""

import hashlib
import uuid
from pathlib import Path

import pytest
from app.models.artifact import Artifact

from packages.storage.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    AzureBlobArtifactStore,
    LocalStorageArtifactStore,
    S3CompatibleArtifactStore,
    create_artifact_store,
)


@pytest.mark.asyncio
async def test_local_storage_store(tmp_path: Path):
    store = LocalStorageArtifactStore(base_dir=tmp_path / "artifacts")
    data = b"def test_app(): assert True\n"
    expected_sha = hashlib.sha256(data).hexdigest()

    # 1. Put
    sha = await store.put("project-1/diff.patch", data, content_type="text/x-diff")
    assert sha == expected_sha
    assert await store.exists("project-1/diff.patch")

    # 2. Get
    retrieved = await store.get("project-1/diff.patch")
    assert retrieved == data

    # 3. Presign URL
    url = await store.presign("project-1/diff.patch", expires_in_seconds=300)
    assert "signature=" in url
    assert "expires=" in url

    # 4. Traversal block
    with pytest.raises(ArtifactStoreError) as exc:
        await store.put("../../etc/passwd", b"malicious")
    assert "Path traversal" in str(exc.value)

    # 5. Delete
    deleted = await store.delete("project-1/diff.patch")
    assert deleted is True
    assert not await store.exists("project-1/diff.patch")

    # 6. Not Found
    with pytest.raises(ArtifactNotFoundError):
        await store.get("project-1/diff.patch")


@pytest.mark.asyncio
async def test_s3_compatible_store():
    store = S3CompatibleArtifactStore(
        endpoint="http://localhost:8333",
        bucket="agent-artifacts",
        access_key="seaweed-key",
        secret_key="seaweed-secret",
    )
    content = b'{"status": "ok"}'
    sha = await store.put("task-1/report.json", content)
    assert sha == hashlib.sha256(content).hexdigest()

    data = await store.get("task-1/report.json")
    assert data == content

    url = await store.presign("task-1/report.json")
    assert "AWSAccessKeyId=seaweed-key" in url
    assert "Signature=" in url

    assert await store.exists("task-1/report.json")
    await store.delete("task-1/report.json")
    assert not await store.exists("task-1/report.json")


@pytest.mark.asyncio
async def test_azure_store():
    store = AzureBlobArtifactStore(
        account_name="testaccount",
        account_key="testkey",
        container_name="artifacts",
    )
    content = b"artifact content"
    sha = await store.put("file.txt", content)
    assert sha == hashlib.sha256(content).hexdigest()
    assert await store.get("file.txt") == content

    url = await store.presign("file.txt")
    assert "testaccount.blob.core.windows.net" in url


def test_create_artifact_store_factory(tmp_path: Path):
    local = create_artifact_store(provider="local", base_dir=tmp_path)
    assert isinstance(local, LocalStorageArtifactStore)

    s3 = create_artifact_store(provider="s3_compatible")
    assert isinstance(s3, S3CompatibleArtifactStore)

    azure = create_artifact_store(provider="azure")
    assert isinstance(azure, AzureBlobArtifactStore)


def test_artifact_orm_model():
    org_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    art = Artifact(
        organization_id=org_id,
        project_id=proj_id,
        storage_key="org/proj/build.log",
        filename="build.log",
        content_type="text/plain",
        size_bytes=1024,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        artifact_type="LOGS",
        metadata_json={"build_id": "123"},
    )
    assert art.filename == "build.log"
    assert art.artifact_type == "LOGS"
    assert art.storage_key == "org/proj/build.log"
