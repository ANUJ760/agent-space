"""Unit tests for M63 (File Upload Security)."""

import uuid

import pytest

from packages.security.uploads import (
    DisallowedFileTypeError,
    FileUploadSecurityError,
    MagicBytesMismatchError,
    MalwareDetectedError,
    UploadSecurityValidator,
)


@pytest.fixture
def validator() -> UploadSecurityValidator:
    return UploadSecurityValidator(max_size_bytes=1024 * 1024)  # 1 MB


def test_valid_file_passes(validator):
    png_content = b"\x89PNG\r\n\x1a\n" + b"sample image payload"
    # Should not raise
    validator.validate_file(
        filename="screenshot.png",
        content=png_content,
        declared_mime_type="image/png",
    )


def test_magic_bytes_mismatch_rejected(validator):
    # Extension claims PNG, but payload is text
    fake_png = b"<?php phpinfo(); ?>"
    with pytest.raises(MagicBytesMismatchError):
        validator.validate_file(
            filename="shell.png",
            content=fake_png,
            declared_mime_type="image/png",
        )


def test_dangerous_extension_rejected(validator):
    for bad_file in ["malware.exe", "script.sh", "backdoor.php", "payload.bat"]:
        with pytest.raises(DisallowedFileTypeError):
            validator.validate_file(
                filename=bad_file,
                content=b"echo hello",
                declared_mime_type="text/plain",
            )


def test_dangerous_mime_rejected(validator):
    with pytest.raises(DisallowedFileTypeError):
        validator.validate_file(
            filename="binary.dat",
            content=b"\x7fELFsomeexecutable",
            declared_mime_type="application/x-executable",
        )


def test_path_traversal_and_null_bytes_rejected(validator):
    bad_names = [
        "../../etc/passwd",
        "..\\windows\\system32",
        "file.png\x00.exe",
        "/etc/shadow",
    ]
    for bad_name in bad_names:
        with pytest.raises(FileUploadSecurityError):
            validator.validate_file(
                filename=bad_name,
                content=b"content",
                declared_mime_type="text/plain",
            )


def test_file_size_limit(validator):
    oversized = b"x" * (1024 * 1024 + 1)
    with pytest.raises(FileUploadSecurityError) as exc:
        validator.validate_file(
            filename="large.txt",
            content=oversized,
            declared_mime_type="text/plain",
        )
    assert "exceeds limit" in str(exc.value)


def test_malware_scanner_eicar(validator):
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with pytest.raises(MalwareDetectedError) as exc:
        validator.validate_file(
            filename="sample.txt",
            content=eicar,
            declared_mime_type="text/plain",
        )
    assert "EICAR-Test-Signature" in str(exc.value)


def test_server_side_storage_key_generation(validator):
    org_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    key = validator.generate_server_storage_key(org_id, proj_id, "my_report.pdf")

    assert str(org_id) in key
    assert str(proj_id) in key
    assert key.endswith(".pdf")
    # Original filename string is NOT in the path
    assert "my_report" not in key
