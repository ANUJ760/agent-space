"""Tests for M01 — Configuration & Environment.

Validates that typed configuration loads successfully, fails fast on invalid values,
masks secrets from string representations and dumps, and covers all required subsystems.
"""

import json
from pathlib import Path

import pytest
from app.config import (
    DatabaseSettings,
    GiteaSettings,
    KeycloakSettings,
    ModelGatewaySettings,
    NatsSettings,
    ObservabilitySettings,
    QdrantSettings,
    RedisSettings,
    SandboxSettings,
    Settings,
    StorageSettings,
    TemporalSettings,
    get_settings,
)
from pydantic import SecretStr, ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_default_settings_load() -> None:
    settings = Settings()
    assert settings.app_name == "Agent Space"
    assert settings.port == 8000
    assert settings.environment == "development"
    assert settings.debug is True

    # Subsystem slices
    assert isinstance(settings.database, DatabaseSettings)
    assert settings.database.url.startswith("postgresql+asyncpg://")

    assert isinstance(settings.redis, RedisSettings)
    assert settings.redis.url.startswith("redis://")

    assert isinstance(settings.nats, NatsSettings)
    assert settings.nats.url.startswith("nats://")

    assert isinstance(settings.temporal, TemporalSettings)
    assert settings.temporal.host == "localhost:7233"

    assert isinstance(settings.keycloak, KeycloakSettings)
    assert settings.keycloak.realm == "agentspace"

    assert isinstance(settings.qdrant, QdrantSettings)
    assert settings.qdrant.collection == "agent_space_memory"

    assert isinstance(settings.storage, StorageSettings)
    assert settings.storage.bucket == "agent-artifacts"

    assert isinstance(settings.gitea, GiteaSettings)
    assert settings.gitea.admin_user == "gitea_admin"

    assert isinstance(settings.model_gateway, ModelGatewaySettings)
    assert settings.model_gateway.provider == "ollama"

    assert isinstance(settings.sandbox, SandboxSettings)
    assert settings.sandbox.type == "docker"

    assert isinstance(settings.observability, ObservabilitySettings)
    assert settings.observability.log_level == "INFO"


def test_get_settings_cached_singleton() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_env_example_contains_all_settings_fields() -> None:
    env_example_path = REPO_ROOT / ".env.example"
    content = env_example_path.read_text()

    # Verify each setting in Settings is represented in .env.example
    field_names = Settings.model_fields.keys()
    for name in field_names:
        env_var_name = name.upper()
        assert env_var_name in content, (
            f"Field '{name}' (env var '{env_var_name}') missing in .env.example"
        )


def test_invalid_database_url_fails_fast() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(database_url="mysql://user:pass@localhost/db")
    errors = str(exc_info.value)
    assert "DATABASE_URL must start with" in errors


def test_invalid_port_fails_fast() -> None:
    with pytest.raises(ValidationError):
        Settings(port=99999)
    with pytest.raises(ValidationError):
        Settings(port=-1)


def test_invalid_log_level_fails_fast() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE")  # type: ignore[arg-type]


def test_invalid_redis_url_fails_fast() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(redis_url="http://localhost:6379")
    assert "REDIS_URL must start with" in str(exc_info.value)


def test_invalid_nats_url_fails_fast() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(nats_url="http://localhost:4222")
    assert "NATS_URL must start with" in str(exc_info.value)


def test_invalid_service_urls_fail_fast() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(keycloak_server_url="ftp://localhost:8080")
    assert "KEYCLOAK_SERVER_URL must start with" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(qdrant_url="grpc://localhost:6333")
    assert "QDRANT_URL must start with" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(gitea_url="ssh://localhost:3001")
    assert "GITEA_URL must start with" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(model_gateway_base_url="tcp://localhost:11434")
    assert "MODEL_GATEWAY_BASE_URL must start with" in str(exc_info.value)


def test_secrets_are_masked_in_str_and_repr() -> None:
    secret_val = "super-secret-password-12345"
    settings = Settings(
        secret_key=SecretStr(secret_val),
        keycloak_client_secret=SecretStr(secret_val),
        storage_secret_key=SecretStr(secret_val),
        gitea_admin_token=SecretStr(secret_val),
    )

    # String representations must NEVER show the secret value
    assert secret_val not in str(settings.secret_key)
    assert secret_val not in repr(settings.secret_key)
    assert secret_val not in str(settings.keycloak_client_secret)
    assert secret_val not in repr(settings.keycloak_client_secret)
    assert secret_val not in str(settings.storage_secret_key)
    assert secret_val not in repr(settings.storage_secret_key)
    assert secret_val not in str(settings.gitea_admin_token)
    assert secret_val not in repr(settings.gitea_admin_token)

    # SecretStr reveals value ONLY via get_secret_value()
    assert settings.secret_key.get_secret_value() == secret_val


def test_safe_dump_masks_secrets() -> None:
    secret_val = "super-sensitive-token"
    settings = Settings(
        secret_key=SecretStr(secret_val),
        gitea_admin_token=SecretStr(secret_val),
    )
    dumped = settings.safe_dump()
    assert secret_val not in json.dumps(dumped)
    assert dumped["secret_key"] == "**********"
    assert dumped["gitea_admin_token"] == "**********"
    assert dumped["app_name"] == "Agent Space"


def test_cors_origins_parsing() -> None:
    # JSON list string
    s1 = Settings(cors_origins='["https://example.com", "https://app.example.com"]')  # type: ignore[arg-type]
    assert s1.cors_origins == ["https://example.com", "https://app.example.com"]

    # Comma-separated string
    s2 = Settings(cors_origins="https://example.com, https://app.example.com")  # type: ignore[arg-type]
    assert s2.cors_origins == ["https://example.com", "https://app.example.com"]

    # Native list
    s3 = Settings(cors_origins=["https://example.com"])
    assert s3.cors_origins == ["https://example.com"]


def test_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("DEBUG", "false")

    settings = Settings()
    assert settings.environment == "production"
    assert settings.port == 9000
    assert settings.log_level == "ERROR"
    assert settings.debug is False
