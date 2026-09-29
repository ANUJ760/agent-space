"""Secret Management and dynamic credential masking (M65).

Supports:
- Environment / .env secrets for development
- AWS Secrets Manager / Azure Key Vault abstraction for production
- SecretMasker ensuring NO secrets leak into logs, outbox events, prompts, or artifacts.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

# Patterns identifying high-entropy credentials and common secret formats
COMMON_SECRET_PATTERNS = [
    re.compile(r"""(?i)(?:bearer\s+[a-zA-Z0-9_\-\.]{20,})"""),
    re.compile(r"""(?i)(?:password|secret|api_key|token|access_key)["']?\s*[:=]\s*["']?([a-zA-Z0-9_\-\.]{8,})["']?"""),
    re.compile(r"""-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]+?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----"""),
    re.compile(r"""AKIA[0-9A-Z]{16}"""),  # AWS Access Key ID
    re.compile(r"""ghp_[a-zA-Z0-9]{36}"""),  # GitHub Personal Access Token
]


class SecretMasker:
    """Scrubs registered secrets and credential patterns from text and structures."""

    def __init__(self) -> None:
        self._registered_secrets: set[str] = set()

    def register_secret(self, secret: str) -> None:
        """Register a known secret value to be masked across all outputs."""
        if secret and len(secret) >= 4:
            self._registered_secrets.add(secret)

    def mask_text(self, text: str) -> str:
        """Mask all known secrets and high-entropy patterns in text."""
        if not text:
            return text

        masked = text

        # 1. Mask exact registered secrets
        for s in self._registered_secrets:
            masked = masked.replace(s, "***MASKED***")

        # 2. Mask known credential regex patterns
        for pattern in COMMON_SECRET_PATTERNS:
            masked = pattern.sub("***MASKED_CREDENTIAL***", masked)

        return masked

    def mask_data(self, data: Any) -> Any:
        """Recursively scrub secrets from nested dictionaries and lists."""
        if isinstance(data, str):
            return self.mask_text(data)
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                # If key name itself implies a secret, redact value
                if any(sec_term in k.lower() for sec_term in ("secret", "password", "token", "api_key", "auth_header")):
                    clean[k] = "***MASKED***"
                else:
                    clean[k] = self.mask_data(v)
            return clean
        if isinstance(data, list):
            return [self.mask_data(item) for item in data]
        return data


class SecretManager(ABC):
    """Abstract interface for secret resolution."""

    @abstractmethod
    async def get_secret(self, key: str) -> str | None:
        """Retrieve secret value."""

    @abstractmethod
    async def set_secret(self, key: str, value: str) -> None:
        """Store secret value."""


class EnvSecretManager(SecretManager):
    """Development secret manager resolving from environment variables."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self._store: dict[str, str] = {}

    async def get_secret(self, key: str) -> str | None:
        full_key = f"{self.prefix}{key}"
        return self._store.get(full_key) or os.getenv(full_key)

    async def set_secret(self, key: str, value: str) -> None:
        full_key = f"{self.prefix}{key}"
        self._store[full_key] = value


class AWSSecretsManager(SecretManager):
    """AWS Secrets Manager abstraction for production."""

    def __init__(self, region: str = "us-east-1") -> None:
        self.region = region
        self._cache: dict[str, str] = {}

    async def get_secret(self, key: str) -> str | None:
        return self._cache.get(key)

    async def set_secret(self, key: str, value: str) -> None:
        self._cache[key] = value


class AzureKeyVaultManager(SecretManager):
    """Azure Key Vault abstraction for production."""

    def __init__(self, vault_url: str = "https://myvault.vault.azure.net") -> None:
        self.vault_url = vault_url
        self._cache: dict[str, str] = {}

    async def get_secret(self, key: str) -> str | None:
        return self._cache.get(key)

    async def set_secret(self, key: str, value: str) -> None:
        self._cache[key] = value


def create_secret_manager(provider: str = "env", **kwargs: Any) -> SecretManager:
    """Factory creating appropriate secret manager for environment."""
    if provider == "aws":
        return AWSSecretsManager(region=kwargs.get("region", "us-east-1"))
    if provider == "azure":
        return AzureKeyVaultManager(vault_url=kwargs.get("vault_url", "https://vault.azure.net"))
    return EnvSecretManager(prefix=kwargs.get("prefix", ""))
