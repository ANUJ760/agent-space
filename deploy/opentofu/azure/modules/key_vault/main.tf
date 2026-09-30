data "azurerm_client_config" "current" {}

resource "random_string" "kv_suffix" {
  length  = 5
  special = false
  upper   = false
}

# Azure Key Vault with Soft Delete and Purge Protection
resource "azurerm_key_vault" "main" {
  name                        = "${lower(substr(replace(var.name_prefix, "-", ""), 0, 18))}kv${random_string.kv_suffix.result}"
  location                    = var.location
  resource_group_name         = var.resource_group_name
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 90
  purge_protection_enabled    = true

  sku_name = "standard"

  # Current deployer access policy
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = [
      "Get", "List", "Set", "Delete", "Purge", "Recover"
    ]
  }

  tags = var.tags
}

# Cryptographically Secure Secrets
resource "random_password" "postgres_password" {
  length  = 32
  special = false
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "database-password"
  value        = random_password.postgres_password.result
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "redis_auth" {
  name         = "redis-auth-token"
  value        = random_password.redis_auth.result
  key_vault_id = azurerm_key_vault.main.id
}
