"""Unit tests for artifact preview service and content sanitization."""

import uuid

from app.services.artifact_preview import (
    ArtifactPreviewService,
    ContentSanitizer,
)


def test_content_sanitizer_xss():
    # Script tag removal
    malicious = "<script>alert('xss')</script>Hello World"
    sanitized = ContentSanitizer.sanitize_html_or_markdown(malicious)
    assert "<script>" not in sanitized
    assert "alert" not in sanitized
    assert "Hello World" in sanitized

    # Event handlers and javascript: URI removal
    malicious_event = '<img src="x" onerror="stealCookies()">'
    assert "onerror" not in ContentSanitizer.sanitize_html_or_markdown(malicious_event)

    malicious_link = '<a href="javascript:doEvil()">click me</a>'
    sanitized_link = ContentSanitizer.sanitize_html_or_markdown(malicious_link)
    assert "javascript:" not in sanitized_link


def test_preview_code_and_truncation():
    service = ArtifactPreviewService(max_preview_bytes=20)
    data = b"line 1\nline 2\nline 3\nline 4\nline 5\n"
    art_id = uuid.uuid4()

    preview = service.generate_preview(
        artifact_id=art_id,
        filename="app.py",
        content_type="text/x-python",
        artifact_type="CODE",
        raw_data=data,
        sha256_hash="dummy_hash",
    )

    assert preview.is_truncated is True
    assert preview.artifact_type == "CODE"
    assert len(str(preview.preview_content)) <= 30


def test_preview_test_results_structured():
    service = ArtifactPreviewService()
    test_json = b'{"total": 10, "passed": 8, "failed": 2}'
    art_id = uuid.uuid4()

    preview = service.generate_preview(
        artifact_id=art_id,
        filename="results.json",
        content_type="application/json",
        artifact_type="TEST_RESULTS",
        raw_data=test_json,
        sha256_hash="dummy_hash",
    )

    assert preview.artifact_type == "TEST_RESULTS"
    assert isinstance(preview.preview_content, dict)
    assert preview.preview_content["passed"] == 8


def test_preview_image():
    service = ArtifactPreviewService()
    art_id = uuid.uuid4()

    preview = service.generate_preview(
        artifact_id=art_id,
        filename="screenshot.png",
        content_type="image/png",
        artifact_type="IMAGE",
        raw_data=b"\x89PNG\r\n\x1a\nfakeimage",
        sha256_hash="fakehash",
        presigned_url="http://localhost:8333/bucket/screenshot.png?sig=123",
    )

    assert preview.artifact_type == "IMAGE"
    assert preview.preview_content is None
    assert "screenshot.png?sig=123" in (preview.presigned_url or "")
