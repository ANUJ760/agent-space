variable "cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
  default     = "agent-space-prod-aks"
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "dns_prefix" {
  description = "DNS prefix for AKS cluster"
  type        = string
  default     = "agentspace-prod"
}

variable "subnet_id" {
  description = "Subnet ID where AKS nodes reside"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.30"
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID for monitoring"
  type        = string
}

variable "node_vm_size" {
  description = "VM size for the default system node pool"
  type        = string
  default     = "Standard_D4s_v5"
}

variable "min_nodes" {
  description = "Minimum nodes in default pool"
  type        = number
  default     = 2
}

variable "max_nodes" {
  description = "Maximum nodes in default pool"
  type        = number
  default     = 10
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
