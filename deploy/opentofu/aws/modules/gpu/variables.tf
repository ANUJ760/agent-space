variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs where GPU nodes reside"
  type        = list(string)
}

variable "node_role_arn" {
  description = "IAM role ARN for the worker nodes"
  type        = string
}

variable "instance_types" {
  description = "GPU instance types (e.g. g5.xlarge, g4dn.xlarge)"
  type        = list(string)
  default     = ["g5.xlarge", "g4dn.xlarge"]
}

variable "min_nodes" {
  description = "Minimum number of GPU nodes (supports scale-to-zero)"
  type        = number
  default     = 0
}

variable "max_nodes" {
  description = "Maximum number of GPU nodes"
  type        = number
  default     = 4
}

variable "desired_nodes" {
  description = "Desired number of GPU nodes"
  type        = number
  default     = 0
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
