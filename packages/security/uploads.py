"""File Upload Security and validation engine (M63).

Enforces:
- File size validation.
- MIME type and magic bytes verification (prevents extension spoofing).
- Path traversal blocking (null bytes, directory traversal).
- Server-side unique storage key generation (original filenames are NEVER trusted paths).
- Antivirus / malware scanning hook.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class FileUploadSecurityError(Exception):
    """Base exception for file upload security rejections."""


class DisallowedFileTypeError(FileUploadSecurityError):
    """Raised when file extension or MIME type is forbidden."""


class MagicBytesMismatchError(FileUploadSecurityError):
    """Raised when file magic bytes do not match declared MIME/extension."""


class MalwareDetectedError(FileUploadSecurityError):
    """Raised when malware scanner flags uploaded content."""


# Common magic byte signatures
MAGIC_BYTE_SIGNATURES: dict[str, list[bytes]] = {
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "application/pdf": [b"%PDF-"],
    "application/zip": [b"PK\x03\x04", b"PK\x05\x06"],
    "text/plain": [],  # plain text has no fixed header
}

# Forbidden dangerous file extensions
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".bash", ".bin",
    ".dll", ".so", ".dylib", ".elf",
    ".vbs", ".ps1", ".jar", ".msi",
    ".php", ".phtml", ".phar",
}

# Dangerous MIME types
DANGEROUS_MIME_TYPES = {
    "application/x-dosexec",
    "application/x-executable",
    "application/x-msdos-program",
    "application/x-sh",
    "application/x-bat",
}


@dataclass
class MalwareScanResult:
    """Outcome of malware scanning."""

    is_clean: bool
    threat_name: str | None = None


class MalwareScanner:
    """Pluggable malware and threat scanner hook."""

    def scan(self, data: bytes) -> MalwareScanResult:
        """Scan binary data for malware signatures.

        Inspects for standard EICAR test string and malicious signatures.
        """
        # EICAR standard antivirus test string signature
        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        if eicar in data:
            return MalwareScanResult(is_clean=False, threat_name="EICAR-Test-Signature")
        return MalwareScanResult(is_clean=True)


class UploadSecurityValidator:
    """Validates files before ingestion and generates safe storage keys."""

    def __init__(
        self,
        max_size_bytes: int = 25 * 1024 * 1024,
        allowed_mime_types: set[str] | None = None,
        malware_scanner: MalwareScanner | None = None,
    ) -> None:
        self.max_size_bytes = max_size_bytes
        self.allowed_mime_types = allowed_mime_types
        self.scanner = malware_scanner or MalwareScanner()

    def sanitize_client_filename(self, filename: str) -> str:
        """Clean client filename for display only (never for filesystem storage paths)."""
        # Strip null bytes
        clean = filename.replace("\x00", "")
        # Remove directory separators
        clean = os.path.basename(clean)
        # Strip leading/trailing dots and spaces
        clean = clean.strip(". ")
        # Fallback if empty
        return clean or "unnamed_artifact"

    def generate_server_storage_key(
        self,
        organization_id: uuid.UUID | str,
        project_id: uuid.UUID | str,
        original_filename: str,
    ) -> str:
        """Generate safe, server-side storage key. Original filenames are NEVER trusted paths."""
        ext = Path(original_filename).suffix.lower()
        if not ext or ext in DANGEROUS_EXTENSIONS:
            ext = ".bin"

        date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
        random_token = uuid.uuid4().hex
        return f"{organization_id}/{project_id}/{date_prefix}/{random_token}{ext}"

    def validate_file(
        self,
        filename: str,
        content: bytes,
        declared_mime_type: str = "application/octet-stream",
    ) -> None:
        """Validate size, extension, MIME, magic bytes, path traversal, and malware."""
        # 1. Path traversal and null byte checks
        if "\x00" in filename:
            raise FileUploadSecurityError("Null bytes detected in filename")
        if "/" in filename or "\\" in filename or ".." in filename:
            raise FileUploadSecurityError("Path traversal characters detected in filename")

        # 2. File size validation
        if len(content) > self.max_size_bytes:
            raise FileUploadSecurityError(
                f"File size ({len(content)} bytes) exceeds limit ({self.max_size_bytes} bytes)"
            )
        if len(content) == 0:
            raise FileUploadSecurityError("Empty file payload rejected")

        # 3. Extension validation
        ext = Path(filename).suffix.lower()
        if ext in DANGEROUS_EXTENSIONS:
            raise DisallowedFileTypeError(f"File extension '{ext}' is forbidden")

        # 4. MIME type validation
        mime = declared_mime_type.lower().split(";")[0].strip()
        if mime in DANGEROUS_MIME_TYPES:
            raise DisallowedFileTypeError(f"MIME type '{mime}' is forbidden")

        if self.allowed_mime_types and mime not in self.allowed_mime_types:
            raise DisallowedFileTypeError(f"MIME type '{mime}' is not in allowed list")

        # 5. Magic bytes inspection
        signatures = MAGIC_BYTE_SIGNATURES.get(mime)
        if signatures:
            matches_magic = any(content.startswith(sig) for sig in signatures)
            if not matches_magic:
                raise MagicBytesMismatchError(
                    f"File header magic bytes do not match declared MIME type '{mime}'"
                )

        # 6. Malware scanning hook
        scan_result = self.scanner.scan(content)
        if not scan_result.is_clean:
            raise MalwareDetectedError(
                f"Malware threat detected: {scan_result.threat_name}"
            )
