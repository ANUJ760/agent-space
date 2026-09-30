variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "vpc_id" {
  description = "VPC ID where Redis cache is deployed"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ElastiCache subnet group"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks permitted to connect to Redis (EKS worker subnets)"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "KMS Key ARN for encryption at rest"
  type        = string
}

variable "node_type" {
  description = "ElastiCache node instance type"
  type        = string
  default     = "cache.r6g.large"
}

variable "num_cache_clusters" {
  description = "Number of cache clusters (1 primary + replicas)"
  type        = number
  default     = 2
}

variable "auth_token" {
  description = "Redis AUTH token (sensitive, managed by Secrets module)"
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
