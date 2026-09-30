output "storage_account_id" {
  description = "Storage Account ID"
  value       = azurerm_storage_account.artifacts.id
}

output "storage_account_name" {
  description = "Storage Account Name"
  value       = azurerm_storage_account.artifacts.name
}

output "container_name" {
  description = "Artifacts Blob Container Name"
  value       = azurerm_storage_container.artifacts.name
}

output "primary_blob_endpoint" {
  description = "Primary Blob Endpoint URL"
  value       = azurerm_storage_account.artifacts.primary_blob_endpoint
}
