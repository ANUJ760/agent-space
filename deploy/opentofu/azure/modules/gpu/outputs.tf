output "node_pool_id" {
  description = "Node pool ID"
  value       = azurerm_kubernetes_cluster_node_pool.gpu.id
}
