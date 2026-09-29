"""Artifact preview service and sanitization logic.

Sanitizes preview data:
- Strips executable HTML, scripts, and javascript: links to prevent stored XSS.
- Truncates oversized previews to protect the UI.
- Formats structured diff, code, log, and test result previews.
"""

from __future__ import annotations

import html
import json
import re
import uuid
from typing import Any

from app.schemas.artifact import ArtifactPreviewResponse

# Max preview size for text/logs/diffs (256 KB)
MAX_PREVIEW_BYTES = 256 * 1024

# Disallowed dangerous tags and attributes
DANGEROUS_TAGS_RE = re.compile(
    r"<\s*(script|style|iframe|embed|object|form|meta|link|base)[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
SELF_CLOSING_DANGEROUS_RE = re.compile(
    r"<\s*(script|style|iframe|embed|object|form|meta|link|base|input)[^>]*\/?>",
    re.IGNORECASE,
)
EVENT_HANDLER_ATTRS_RE = re.compile(
    r"""(?:\s+on\w+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+))""",
    re.IGNORECASE,
)
JAVASCRIPT_URI_RE = re.compile(
    r"""(?:href|src|data)\s*=\s*['"]\s*javascript:[^'"]*['"]""",
    re.IGNORECASE,
)


class ContentSanitizer:
    """Sanitizes text and document content before preview rendering."""

    @classmethod
    def sanitize_html_or_markdown(cls, raw: str) -> str:
        """Strip dangerous script tags, event handlers, and javascript: links."""
        sanitized = DANGEROUS_TAGS_RE.sub("", raw)
        sanitized = SELF_CLOSING_DANGEROUS_RE.sub("", sanitized)
        sanitized = EVENT_HANDLER_ATTRS_RE.sub("", sanitized)
        sanitized = JAVASCRIPT_URI_RE.sub('href="#"', sanitized)
        return sanitized

    @classmethod
    def sanitize_plain_text(cls, raw: str) -> str:
        """HTML-escape raw plaintext for safe web display."""
        return html.escape(raw)


class ArtifactPreviewService:
    """Generates sanitized, truncated previews for diverse artifact types."""

    def __init__(self, max_preview_bytes: int = MAX_PREVIEW_BYTES) -> None:
        self.max_preview_bytes = max_preview_bytes

    def generate_preview(
        self,
        artifact_id: uuid.UUID,
        filename: str,
        content_type: str,
        artifact_type: str,
        raw_data: bytes,
        sha256_hash: str,
        presigned_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ArtifactPreviewResponse:
        """Create a sanitized preview response for the requested artifact."""
        size_bytes = len(raw_data)
        is_truncated = size_bytes > self.max_preview_bytes
        truncated_bytes = raw_data[: self.max_preview_bytes]

        preview_content: str | dict[str, Any] | None = None
        upper_type = artifact_type.upper()

        if upper_type == "IMAGE":
            # For images, preview_content is None; frontend renders the presigned_url
            preview_content = None

        elif upper_type in ("CODE", "DIFF", "LOGS"):
            text = truncated_bytes.decode("utf-8", errors="replace")
            # Sanitize to plain text
            preview_content = ContentSanitizer.sanitize_plain_text(text)

        elif upper_type == "TEST_RESULTS":
            text = truncated_bytes.decode("utf-8", errors="replace")
            try:
                # Try parsing structured JSON test results
                parsed = json.loads(text)
                preview_content = parsed
            except Exception:
                preview_content = ContentSanitizer.sanitize_plain_text(text)

        elif upper_type == "DOCUMENT":
            text = truncated_bytes.decode("utf-8", errors="replace")
            # Allow safe markdown, strip malicious HTML/scripts
            preview_content = ContentSanitizer.sanitize_html_or_markdown(text)

        else:
            # Default fallback
            text = truncated_bytes.decode("utf-8", errors="replace")
            preview_content = ContentSanitizer.sanitize_plain_text(text)

        return ArtifactPreviewResponse(
            artifact_id=artifact_id,
            artifact_type=upper_type,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            preview_content=preview_content,
            is_truncated=is_truncated,
            presigned_url=presigned_url,
            metadata_json=metadata_json or {},
        )
