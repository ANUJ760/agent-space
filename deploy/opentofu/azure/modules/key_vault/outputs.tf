output "key_vault_id" {
  description = "Key Vault ID"
  value       = azurerm_key_vault.main.id
}

output "key_vault_uri" {
  description = "Key Vault Vault URI"
  value       = azurerm_key_vault.main.vault_uri
}

output "database_password_secret_id" {
  description = "Secret ID for database password"
  value       = azurerm_key_vault_secret.postgres_password.id
}

output "database_password" {
  description = "Database master password for PostgreSQL Flexible Server"
  value       = random_password.postgres_password.result
  sensitive   = true
}

output "redis_auth_token" {
  description = "Redis AUTH token"
  value       = random_password.redis_auth.result
  sensitive   = true
}
