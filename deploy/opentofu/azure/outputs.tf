# ==============================================================================
# Agent Space - Azure OpenTofu Outputs
# ==============================================================================
# Security requirement (Section 94): "Do not output secrets."
# Zero passwords, private keys, auth tokens, or plaintext credentials exported.
# ==============================================================================

output "resource_group_name" {
  description = "Azure Resource Group name"
  value       = azurerm_resource_group.main.name
}

output "vnet_id" {
  description = "Virtual Network ID"
  value       = module.vnet.vnet_id
}

output "aks_cluster_name" {
  description = "AKS Cluster name"
  value       = module.aks.cluster_name
}

output "postgresql_server_fqdn" {
  description = "PostgreSQL Flexible Server FQDN"
  value       = module.postgresql.server_fqdn
}

output "storage_account_name" {
  description = "Storage Account name for artifacts"
  value       = module.blob.storage_account_name
}

output "key_vault_uri" {
  description = "Azure Key Vault URI"
  value       = module.key_vault.key_vault_uri
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID"
  value       = module.monitoring.log_analytics_workspace_id
}
