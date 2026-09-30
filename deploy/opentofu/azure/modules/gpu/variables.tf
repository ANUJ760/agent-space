variable "cluster_id" {
  description = "AKS Cluster ID"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for the GPU node pool"
  type        = string
}

variable "vm_size" {
  description = "VM size with NVIDIA GPU support"
  type        = string
  default     = "Standard_NC4as_T4_v3"
}

variable "min_nodes" {
  description = "Minimum nodes in GPU pool (supports scale-to-zero)"
  type        = number
  default     = 0
}

variable "max_nodes" {
  description = "Maximum nodes in GPU pool"
  type        = number
  default     = 4
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
