output "vnet_id" {
  description = "Virtual Network ID"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Virtual Network Name"
  value       = azurerm_virtual_network.main.name
}

output "aks_subnet_id" {
  description = "Subnet ID for AKS cluster"
  value       = azurerm_subnet.aks.id
}

output "postgres_subnet_id" {
  description = "Subnet ID delegated to PostgreSQL Flexible Server"
  value       = azurerm_subnet.postgres.id
}

output "ingress_subnet_id" {
  description = "Subnet ID for ingress"
  value       = azurerm_subnet.ingress.id
}
