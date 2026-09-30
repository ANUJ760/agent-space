# Dedicated GPU Node Pool for LLM Inference & Vision Agent
resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  name                  = "gpunodes"
  kubernetes_cluster_id = var.cluster_id
  vm_size               = var.vm_size
  vnet_subnet_id        = var.subnet_id
  os_type               = "Linux"
  os_sku                = "Ubuntu"

  enable_auto_scaling = true
  min_count           = var.min_nodes
  max_count           = var.max_nodes

  node_labels = {
    accelerator = "nvidia-gpu"
    workload    = "llm-inference"
  }

  node_taints = [
    "nvidia.com/gpu=true:NoSchedule"
  ]

  tags = var.tags
}
