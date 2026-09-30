output "cluster_id" {
  description = "AKS Cluster ID"
  value       = azurerm_kubernetes_cluster.main.id
}

output "cluster_name" {
  description = "AKS Cluster Name"
  value       = azurerm_kubernetes_cluster.main.name
}

output "oidc_issuer_url" {
  description = "OIDC Issuer URL for Azure Workload Identity"
  value       = azurerm_kubernetes_cluster.main.oidc_issuer_url
}

output "key_vault_secrets_provider_client_id" {
  description = "Client ID of the Key Vault Secrets Provider identity"
  value       = azurerm_kubernetes_cluster.main.key_vault_secrets_provider[0].secret_identity[0].client_id
}

output "node_resource_group" {
  description = "Resource group hosting AKS infrastructure nodes"
  value       = azurerm_kubernetes_cluster.main.node_resource_group
}
