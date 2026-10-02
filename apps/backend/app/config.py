"""Centralized typed configuration for Agent Space backend.

Exposes typed configuration models for all 11 core subsystems:
database, redis, nats, temporal, keycloak, qdrant, storage, gitea,
model gateway, sandbox, and observability.
"""

import json
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """PostgreSQL authoritative state settings."""

    url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agentspace",
        description="Async database connection string",
    )
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=300)
    echo: bool = Field(default=False)

    @field_validator("url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql+asyncpg://") or v.startswith("sqlite+aiosqlite://")):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql+asyncpg://' (or 'sqlite+aiosqlite://' for testing)"
            )
        return v


class RedisSettings(BaseModel):
    """Redis ephemeral state and cache settings."""

    url: str = Field(default="redis://localhost:6379/0")
    pool_size: int = Field(default=10, ge=1, le=100)
    timeout: int = Field(default=5, ge=1, le=60)

    @field_validator("url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not (v.startswith("redis://") or v.startswith("rediss://")):
            raise ValueError("REDIS_URL must start with 'redis://' or 'rediss://'")
        return v


class NatsSettings(BaseModel):
    """NATS JetStream event messaging settings."""

    url: str = Field(default="nats://localhost:4222")
    stream_name: str = Field(default="AGENT_SPACE_EVENTS")
    consumer_group: str = Field(default="agentspace-backend")

    @field_validator("url")
    @classmethod
    def validate_nats_url(cls, v: str) -> str:
        if not (v.startswith("nats://") or v.startswith("tls://")):
            raise ValueError("NATS_URL must start with 'nats://' or 'tls://'")
        return v


class TemporalSettings(BaseModel):
    """Temporal durable workflow engine settings."""

    host: str = Field(default="localhost:7233")
    namespace: str = Field(default="default")
    task_queue: str = Field(default="agent-space-tasks")


class KeycloakSettings(BaseModel):
    """Keycloak OIDC and authentication settings."""

    server_url: str = Field(default="http://localhost:8080")
    realm: str = Field(default="agentspace")
    client_id: str = Field(default="agentspace-backend")
    client_secret: SecretStr = Field(default=SecretStr("keycloak-client-secret-placeholder"))
    audience: str = Field(default="agentspace-backend")

    @field_validator("server_url")
    @classmethod
    def validate_keycloak_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("KEYCLOAK_SERVER_URL must start with 'http://' or 'https://'")
        return v


class QdrantSettings(BaseModel):
    """Qdrant semantic vector memory settings."""

    url: str = Field(default="http://localhost:6333")
    api_key: SecretStr | None = Field(default=None)
    collection: str = Field(default="agent_space_memory")

    @field_validator("url")
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("QDRANT_URL must start with 'http://' or 'https://'")
        return v


class StorageSettings(BaseModel):
    """Artifact and blob storage settings (SeaweedFS / S3 / Azure)."""

    provider: Literal["s3_compatible", "s3", "azure", "local"] = Field(default="s3_compatible")
    endpoint: str = Field(default="http://localhost:8333")
    bucket: str = Field(default="agent-artifacts")
    access_key: str = Field(default="seaweedfs-access")
    secret_key: SecretStr = Field(default=SecretStr("seaweedfs-secret"))
    region: str = Field(default="us-east-1")
    use_ssl: bool = Field(default=False)


class GiteaSettings(BaseModel):
    """Gitea source control and workspace settings."""

    url: str = Field(default="http://localhost:3001")
    admin_user: str = Field(default="gitea_admin")
    admin_token: SecretStr = Field(default=SecretStr("gitea-admin-token-placeholder"))

    @field_validator("url")
    @classmethod
    def validate_gitea_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("GITEA_URL must start with 'http://' or 'https://'")
        return v


class ModelGatewaySettings(BaseModel):
    """Model Gateway LLM abstraction settings."""

    provider: Literal["ollama", "vllm", "openai_compatible"] = Field(default="ollama")
    base_url: str = Field(default="http://localhost:11434")
    api_key: SecretStr | None = Field(default=None)
    default_chat_model: str = Field(default="llama3.1:8b")
    default_code_model: str = Field(default="qwen2.5-coder:7b")
    default_embedding_model: str = Field(default="nomic-embed-text")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)

    @field_validator("base_url")
    @classmethod
    def validate_model_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("MODEL_GATEWAY_BASE_URL must start with 'http://' or 'https://'")
        return v


class AgentModelDefaults(BaseModel):
    """Defaults advertised to clients for user-supplied (BYOK) agent providers.

    These values are public: the browser uses them to pre-fill the "Add Agent"
    form. No secret ever lives here — API keys stay in the user's browser.
    """

    provider: Literal["gemini"] = Field(default="gemini")
    model: str = Field(default="gemini-2.5-flash")
    base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    user_supplied_keys_enabled: bool = Field(default=True)
    free_tier_models: tuple[str, ...] = (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    )

    @field_validator("base_url")
    @classmethod
    def validate_gemini_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("GEMINI_API_BASE_URL must start with 'http://' or 'https://'")
        return v


class SandboxSettings(BaseModel):
    """Tool execution sandbox settings."""

    type: Literal["docker", "gvisor", "local"] = Field(default="docker")
    docker_image: str = Field(default="python:3.11-slim")
    network_isolation: bool = Field(default=True)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_memory_mb: int = Field(default=1024, ge=128, le=65536)
    max_cpus: float = Field(default=1.0, ge=0.1, le=64.0)


class ObservabilitySettings(BaseModel):
    """Telemetry, tracing, and structured logging settings."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")
    otel_enabled: bool = Field(default=False)
    otel_service_name: str = Field(default="agent-space-backend")
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    prometheus_metrics_enabled: bool = Field(default=True)


class Settings(BaseSettings):
    """Centralized typed configuration for Agent Space backend."""

    # 1. Core Application
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True
    app_name: str = "Agent Space"
    app_version: str = "0.1.0"
    secret_key: SecretStr = Field(
        default=SecretStr("change-this-to-a-secure-random-32-byte-hex-string-for-prod")
    )
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # 2. Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentspace"
    database_pool_size: int = Field(default=20, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=30, ge=1, le=300)
    database_echo: bool = False

    # 3. Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = Field(default=10, ge=1, le=100)
    redis_timeout: int = Field(default=5, ge=1, le=60)

    # 4. NATS
    nats_url: str = "nats://localhost:4222"
    nats_auth_token: SecretStr | None = None
    nats_stream_name: str = "AGENT_SPACE_EVENTS"
    nats_consumer_group: str = "agentspace-backend"

    # 5. Temporal
    temporal_host: str = "localhost:7233"
    temporal_api_key: SecretStr | None = None
    temporal_tls: bool = False
    temporal_namespace: str = "default"
    temporal_task_queue: str = "agent-space-tasks"

    # 6. Keycloak
    keycloak_server_url: str = "http://localhost:8080"
    keycloak_realm: str = "agentspace"
    keycloak_client_id: str = "agentspace-backend"
    keycloak_client_secret: SecretStr = Field(
        default=SecretStr("keycloak-client-secret-placeholder")
    )
    keycloak_audience: str = "agentspace-backend"

    # 7. Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "agent_space_memory"

    # 8. Storage
    storage_provider: Literal["s3_compatible", "s3", "azure", "local"] = "s3_compatible"
    storage_endpoint: str = "http://localhost:8333"
    storage_bucket: str = "agent-artifacts"
    storage_access_key: str = "seaweedfs-access"
    storage_secret_key: SecretStr = Field(default=SecretStr("seaweedfs-secret"))
    storage_region: str = "us-east-1"
    storage_use_ssl: bool = False

    # 9. Gitea
    gitea_url: str = "http://localhost:3001"
    gitea_admin_user: str = "gitea_admin"
    gitea_admin_token: SecretStr = Field(default=SecretStr("gitea-admin-token-placeholder"))

    # 10. Model Gateway
    model_gateway_provider: Literal["ollama", "vllm", "openai_compatible"] = "ollama"
    model_gateway_base_url: str = "http://localhost:11434"
    model_gateway_api_key: SecretStr | None = None
    default_chat_model: str = "llama3.1:8b"
    default_code_model: str = "qwen2.5-coder:7b"
    default_embedding_model: str = "nomic-embed-text"
    model_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    model_max_tokens: int = Field(default=4096, ge=1, le=128000)

    # 10b. User-supplied (BYOK) agent providers — agent inference runs client-side
    default_agent_provider: Literal["gemini"] = "gemini"
    default_agent_model: str = "gemini-2.5-flash"
    default_gemini_api_key: SecretStr | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    user_supplied_api_keys_enabled: bool = True
    # Shared workspace volume. Mount an AWS EFS access point here in production.
    workspace_root: str = "./var/workspaces"
    git_allowed_hosts: str = "github.com,gitlab.com,bitbucket.org"

    # 11. Sandbox
    sandbox_type: Literal["docker", "gvisor", "local"] = "docker"
    sandbox_docker_image: str = "python:3.11-slim"
    sandbox_network_isolation: bool = True
    sandbox_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    sandbox_max_memory_mb: int = Field(default=1024, ge=128, le=65536)
    sandbox_max_cpus: float = Field(default=1.0, ge=0.1, le=64.0)

    # 12. Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    otel_enabled: bool = False
    otel_service_name: str = "agent-space-backend"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_metrics_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.environment == "production" and (
            len(self.secret_key.get_secret_value()) < 32
            or self.secret_key.get_secret_value()
            == "change-this-to-a-secure-random-32-byte-hex-string-for-prod"
        ):
            raise ValueError(
                "Production SECRET_KEY must be a unique value of at least 32 characters"
            )
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v]
        raise ValueError("Invalid cors_origins format")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql+asyncpg://") or v.startswith("sqlite+aiosqlite://")):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql+asyncpg://' (or 'sqlite+aiosqlite://' for testing)"
            )
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not (v.startswith("redis://") or v.startswith("rediss://")):
            raise ValueError("REDIS_URL must start with 'redis://' or 'rediss://'")
        return v

    @field_validator("nats_url")
    @classmethod
    def validate_nats_url(cls, v: str) -> str:
        if not (v.startswith("nats://") or v.startswith("tls://")):
            raise ValueError("NATS_URL must start with 'nats://' or 'tls://'")
        return v

    @field_validator("keycloak_server_url")
    @classmethod
    def validate_keycloak_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("KEYCLOAK_SERVER_URL must start with 'http://' or 'https://'")
        return v

    @field_validator("qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("QDRANT_URL must start with 'http://' or 'https://'")
        return v

    @field_validator("gitea_url")
    @classmethod
    def validate_gitea_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("GITEA_URL must start with 'http://' or 'https://'")
        return v

    @field_validator("model_gateway_base_url")
    @classmethod
    def validate_model_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("MODEL_GATEWAY_BASE_URL must start with 'http://' or 'https://'")
        return v

    # --------------------------------------------------------------------------
    # Subsystem Slices
    # --------------------------------------------------------------------------

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout=self.database_pool_timeout,
            echo=self.database_echo,
        )

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(
            url=self.redis_url,
            pool_size=self.redis_pool_size,
            timeout=self.redis_timeout,
        )

    @property
    def nats(self) -> NatsSettings:
        return NatsSettings(
            url=self.nats_url,
            stream_name=self.nats_stream_name,
            consumer_group=self.nats_consumer_group,
        )

    @property
    def temporal(self) -> TemporalSettings:
        return TemporalSettings(
            host=self.temporal_host,
            namespace=self.temporal_namespace,
            task_queue=self.temporal_task_queue,
        )

    @property
    def keycloak(self) -> KeycloakSettings:
        return KeycloakSettings(
            server_url=self.keycloak_server_url,
            realm=self.keycloak_realm,
            client_id=self.keycloak_client_id,
            client_secret=self.keycloak_client_secret,
            audience=self.keycloak_audience,
        )

    @property
    def qdrant(self) -> QdrantSettings:
        return QdrantSettings(
            url=self.qdrant_url,
            api_key=self.qdrant_api_key,
            collection=self.qdrant_collection,
        )

    @property
    def storage(self) -> StorageSettings:
        return StorageSettings(
            provider=self.storage_provider,
            endpoint=self.storage_endpoint,
            bucket=self.storage_bucket,
            access_key=self.storage_access_key,
            secret_key=self.storage_secret_key,
            region=self.storage_region,
            use_ssl=self.storage_use_ssl,
        )

    @property
    def gitea(self) -> GiteaSettings:
        return GiteaSettings(
            url=self.gitea_url,
            admin_user=self.gitea_admin_user,
            admin_token=self.gitea_admin_token,
        )

    @property
    def model_gateway(self) -> ModelGatewaySettings:
        return ModelGatewaySettings(
            provider=self.model_gateway_provider,
            base_url=self.model_gateway_base_url,
            api_key=self.model_gateway_api_key,
            default_chat_model=self.default_chat_model,
            default_code_model=self.default_code_model,
            default_embedding_model=self.default_embedding_model,
            temperature=self.model_temperature,
            max_tokens=self.model_max_tokens,
        )

    @property
    def agent_model_defaults(self) -> AgentModelDefaults:
        return AgentModelDefaults(
            provider=self.default_agent_provider,
            model=self.default_agent_model,
            base_url=self.gemini_api_base_url,
            user_supplied_keys_enabled=self.user_supplied_api_keys_enabled,
        )

    @property
    def sandbox(self) -> SandboxSettings:
        return SandboxSettings(
            type=self.sandbox_type,
            docker_image=self.sandbox_docker_image,
            network_isolation=self.sandbox_network_isolation,
            timeout_seconds=self.sandbox_timeout_seconds,
            max_memory_mb=self.sandbox_max_memory_mb,
            max_cpus=self.sandbox_max_cpus,
        )

    @property
    def observability(self) -> ObservabilitySettings:
        return ObservabilitySettings(
            log_level=self.log_level,
            log_format=self.log_format,
            otel_enabled=self.otel_enabled,
            otel_service_name=self.otel_service_name,
            otel_exporter_otlp_endpoint=self.otel_exporter_otlp_endpoint,
            prometheus_metrics_enabled=self.prometheus_metrics_enabled,
        )

    def safe_dump(self) -> dict[str, Any]:
        """Produce a dictionary representation masking all secrets for diagnostic logging."""
        dump = self.model_dump()
        # Explicitly mask all SecretStr fields
        for key, val in dump.items():
            if isinstance(val, SecretStr) or (
                ("secret" in key or "token" in key or "password" in key or "key" in key)
                and val is not None
                and not key.endswith("_url")
                and not key.endswith("_path")
            ):
                dump[key] = "**********"
        return dump


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton application settings instance."""
    return Settings()
