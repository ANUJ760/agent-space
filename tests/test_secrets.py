"""Unit tests for M65: Secret Management & Masking."""

import os

import pytest

from packages.security.secrets import (
    AWSSecretsManager,
    AzureKeyVaultManager,
    EnvSecretManager,
    SecretMasker,
    create_secret_manager,
)


@pytest.mark.asyncio
async def test_env_secret_manager():
    os.environ["TEST_DB_PASSWORD"] = "pg_secret_123"
    manager = EnvSecretManager()

    val = await manager.get_secret("TEST_DB_PASSWORD")
    assert val == "pg_secret_123"

    await manager.set_secret("TEST_API_KEY", "local_key_456")
    val2 = await manager.get_secret("TEST_API_KEY")
    assert val2 == "local_key_456"

    # Prefix support
    prefixed_manager = EnvSecretManager(prefix="AGENT_SPACE_")
    os.environ["AGENT_SPACE_SIGNING_KEY"] = "token_sign_abc"
    val3 = await prefixed_manager.get_secret("SIGNING_KEY")
    assert val3 == "token_sign_abc"


@pytest.mark.asyncio
async def test_cloud_secret_managers():
    # AWS Secrets Manager
    aws_mgr = create_secret_manager("aws", region="eu-central-1")
    assert isinstance(aws_mgr, AWSSecretsManager)
    await aws_mgr.set_secret("PROD_DATABASE_URL", "postgresql://user:pass@aws-rds:5432/db")
    val_aws = await aws_mgr.get_secret("PROD_DATABASE_URL")
    assert val_aws == "postgresql://user:pass@aws-rds:5432/db"

    # Azure Key Vault
    azure_mgr = create_secret_manager("azure", vault_url="https://agentspace.vault.azure.net")
    assert isinstance(azure_mgr, AzureKeyVaultManager)
    await azure_mgr.set_secret("OPENAI_KEY", "sk-azure-openai-key-999")
    val_azure = await azure_mgr.get_secret("OPENAI_KEY")
    assert val_azure == "sk-azure-openai-key-999"

    # Default factory fallback to env
    default_mgr = create_secret_manager("env")
    assert isinstance(default_mgr, EnvSecretManager)


def test_secret_masker_registered_values():
    masker = SecretMasker()
    masker.register_secret("super_sensitive_api_token_xyz")
    masker.register_secret("database_password_99")

    log_entry = "Connection failed with password=database_password_99 and token=super_sensitive_api_token_xyz"
    scrubbed = masker.mask_text(log_entry)

    assert "database_password_99" not in scrubbed
    assert "super_sensitive_api_token_xyz" not in scrubbed
    assert "***MASKED***" in scrubbed


def test_secret_masker_regex_patterns():
    masker = SecretMasker()

    # Bearer token
    text1 = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    scrubbed1 = masker.mask_text(text1)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed1

    # AWS Key
    text2 = "AWS credentials: AKIAIOSFODNN7EXAMPLE logged."
    scrubbed2 = masker.mask_text(text2)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed2

    # GitHub token
    text3 = "Cloning with token ghp_123456789012345678901234567890123456"
    scrubbed3 = masker.mask_text(text3)
    assert "ghp_123456789012345678901234567890123456" not in scrubbed3


def test_secret_masker_nested_structures():
    masker = SecretMasker()
    masker.register_secret("plain_secret_123")

    payload = {
        "event": "user_action",
        "api_key": "topsecret_api_key_val",
        "nested": {
            "password": "db_password_456",
            "message": "Attempted login with plain_secret_123",
            "tags": ["prod", "plain_secret_123"],
        },
    }

    clean = masker.mask_data(payload)

    # Key-based masking
    assert clean["api_key"] == "***MASKED***"
    assert clean["nested"]["password"] == "***MASKED***"

    # Value-based masking in strings and lists
    assert "plain_secret_123" not in clean["nested"]["message"]
    assert "***MASKED***" in clean["nested"]["message"]
    assert clean["nested"]["tags"] == ["prod", "***MASKED***"]
