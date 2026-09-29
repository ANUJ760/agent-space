"""Tests for M71: Loki Structured JSON Logging and Credential Scrubbing."""

import io
import json
import logging
from pathlib import Path

from app.logging import redact_sensitive_data_processor, setup_logging


def test_redact_sensitive_data_processor():
    raw_event = {
        "event": "user_authenticated",
        "username": "alice",
        "password": "super_secret_password_123",
        "api_key": "sk-proj-1234567890abcdef1234",
        "refresh_token": "rt_secret_token_val_999",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "aws_secret": "AKIAIOSFODNN7EXAMPLE",
        "nested": {
            "token": "sensitive_nested_token",
            "message": "Connected with password=secret_pw_999",
        },
    }

    clean_event = redact_sensitive_data_processor(None, "info", raw_event)

    # Key-based redacting
    assert clean_event["password"] == "***MASKED***"
    assert clean_event["api_key"] == "***MASKED***"
    assert clean_event["refresh_token"] == "***MASKED***"
    assert clean_event["nested"]["token"] == "***MASKED***"

    # Pattern-based redacting
    assert "AKIAIOSFODNN7EXAMPLE" not in str(clean_event)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in str(clean_event)


def test_json_logging_output():
    # Capture stdout
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)

    setup_logging(log_level="INFO", log_format="json")
    root = logging.getLogger()
    if root.handlers:
        handler.setFormatter(root.handlers[0].formatter)
    root.handlers.clear()
    root.addHandler(handler)

    import structlog
    logger = structlog.get_logger("test.audit")
    logger.info("system_boot", component="api", secret_token="my_token_value_abc")

    output = stream.getvalue().strip()
    assert output, "Log output should not be empty"

    # Verify log line is valid JSON
    parsed = json.loads(output)
    assert parsed["event"] == "system_boot"
    assert parsed["component"] == "api"
    assert parsed["secret_token"] == "***MASKED***"
    assert "timestamp" in parsed
    assert parsed["level"] == "info"


def test_loki_configs_validity():
    loki_cfg = Path("infrastructure/loki/loki-config.yml")
    assert loki_cfg.exists(), "Loki config missing"
    assert "http_listen_port: 3100" in loki_cfg.read_text(encoding="utf-8")

    promtail_cfg = Path("infrastructure/loki/promtail-config.yml")
    assert promtail_cfg.exists(), "Promtail config missing"
    assert "agentspace-backend" in promtail_cfg.read_text(encoding="utf-8")
