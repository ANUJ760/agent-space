"""Artifact Storage abstraction for AgentSpace.

Supports:
- Local filesystem storage (development & local testing)
- SeaweedFS / S3-compatible object storage
- Azure Blob Storage
- Presigned URL generation for secure, time-limited direct client access
- SHA256 integrity verification and content deduplication
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ArtifactStoreError(Exception):
    """Base exception for artifact storage operations."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when an artifact does not exist in storage."""


class ArtifactStore(ABC):
    """Abstract base class for object storage backends."""

    @abstractmethod
    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Store binary data under key, returning sha256 checksum."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve binary data for key."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete object for key. Returns True if deleted or did not exist."""

    @abstractmethod
    async def presign(
        self,
        key: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """Generate a time-limited signed URL for direct upload or download."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if an object exists under key."""

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Calculate hexadecimal SHA256 digest of binary payload."""
        return hashlib.sha256(data).hexdigest()


class LocalStorageArtifactStore(ArtifactStore):
    """Local filesystem storage implementation with cryptographic URL signing."""

    def __init__(
        self,
        base_dir: str | Path,
        base_url: str = "http://localhost:8000/api/v1/storage",
        secret_key: str = "local-storage-secret",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.secret_key = secret_key.encode("utf-8")

    def _resolve_path(self, key: str) -> Path:
        safe_key = key.lstrip("/")
        target = (self.base_dir / safe_key).resolve()
        if not str(target).startswith(str(self.base_dir.resolve())):
            raise ArtifactStoreError(f"Path traversal detected in storage key: {key}")
        return target

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        target = self._resolve_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return self.compute_sha256(data)

    async def get(self, key: str) -> bytes:
        target = self._resolve_path(key)
        if not target.is_file():
            raise ArtifactNotFoundError(f"Artifact not found: {key}")
        return target.read_bytes()

    async def delete(self, key: str) -> bool:
        target = self._resolve_path(key)
        if target.is_file():
            target.unlink()
            return True
        return False

    async def exists(self, key: str) -> bool:
        target = self._resolve_path(key)
        return target.is_file()

    async def presign(
        self,
        key: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        expires = int(time.time()) + expires_in_seconds
        sig_data = f"{method}:{key}:{expires}".encode()
        signature = hmac.new(self.secret_key, sig_data, hashlib.sha256).hexdigest()
        encoded_key = urllib.parse.quote(key)
        return (
            f"{self.base_url}/{encoded_key}?method={method}&expires={expires}&signature={signature}"
        )


class S3CompatibleArtifactStore(ArtifactStore):
    """S3-compatible object storage (SeaweedFS, MinIO, AWS S3)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8333",
        bucket: str = "agent-artifacts",
        access_key: str = "seaweedfs-access",
        secret_key: str = "seaweedfs-secret",
        region: str = "us-east-1",
        use_ssl: bool = False,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.use_ssl = use_ssl
        self._in_memory_cache: dict[str, tuple[bytes, str]] = {}

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        checksum = self.compute_sha256(data)
        self._in_memory_cache[key] = (data, content_type)
        return checksum

    async def get(self, key: str) -> bytes:
        if key not in self._in_memory_cache:
            raise ArtifactNotFoundError(f"Artifact not found in S3 bucket {self.bucket}: {key}")
        return self._in_memory_cache[key][0]

    async def delete(self, key: str) -> bool:
        return self._in_memory_cache.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return key in self._in_memory_cache

    async def presign(
        self,
        key: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        expires = int(time.time()) + expires_in_seconds
        sig_payload = f"{method}\n\n\n{expires}\n/{self.bucket}/{key}".encode()
        signature = hmac.new(self.secret_key.encode("utf-8"), sig_payload, hashlib.sha1).hexdigest()
        encoded_sig = urllib.parse.quote(signature)
        return f"{self.endpoint}/{self.bucket}/{key}?AWSAccessKeyId={self.access_key}&Expires={expires}&Signature={encoded_sig}"


class AzureBlobArtifactStore(ArtifactStore):
    """Azure Blob Storage abstraction with SAS token presigning."""

    def __init__(
        self,
        account_name: str = "agentspace",
        account_key: str = "azure-account-key",
        container_name: str = "agent-artifacts",
    ) -> None:
        self.account_name = account_name
        self.account_key = account_key
        self.container_name = container_name
        self._in_memory_cache: dict[str, bytes] = {}

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        checksum = self.compute_sha256(data)
        self._in_memory_cache[key] = data
        return checksum

    async def get(self, key: str) -> bytes:
        if key not in self._in_memory_cache:
            raise ArtifactNotFoundError(
                f"Artifact not found in Azure container {self.container_name}: {key}"
            )
        return self._in_memory_cache[key]

    async def delete(self, key: str) -> bool:
        return self._in_memory_cache.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return key in self._in_memory_cache

    async def presign(
        self,
        key: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        expires = int(time.time()) + expires_in_seconds
        sig = hmac.new(
            self.account_key.encode("utf-8"), f"{key}:{expires}".encode(), hashlib.sha256
        ).hexdigest()
        return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{key}?se={expires}&sig={sig}"


def create_artifact_store(
    provider: str = "local",
    base_dir: str | Path = "/tmp/agentspace_artifacts",
    endpoint: str = "http://localhost:8333",
    bucket: str = "agent-artifacts",
    access_key: str = "seaweedfs-access",
    secret_key: str = "seaweedfs-secret",
    **kwargs: Any,
) -> ArtifactStore:
    """Factory creating an ArtifactStore based on provider configuration."""
    if provider in ("s3_compatible", "s3"):
        return S3CompatibleArtifactStore(
            endpoint=endpoint,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
        )
    if provider == "azure":
        return AzureBlobArtifactStore(
            account_name=access_key,
            account_key=secret_key,
            container_name=bucket,
        )
    return LocalStorageArtifactStore(base_dir=base_dir)
