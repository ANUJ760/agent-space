variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "vpc_id" {
  description = "VPC ID where database is deployed"
  type        = string
}

variable "subnet_ids" {
  description = "Isolated database subnet IDs"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks permitted to connect to PostgreSQL (EKS worker subnets)"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "KMS Key ARN for storage encryption"
  type        = string
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 100
}

variable "max_allocated_storage" {
  description = "Maximum storage autoscaling limit in GB"
  type        = number
  default     = 1000
}

variable "database_name" {
  description = "Initial database name"
  type        = string
  default     = "agentspace"
}

variable "admin_username" {
  description = "Master database username"
  type        = string
  default     = "agentspace_admin"
}

variable "admin_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

variable "multi_az" {
  description = "Enable Multi-AZ high availability deployment"
  type        = bool
  default     = true
}

variable "backup_retention_period" {
  description = "Days of automated backup retention"
  type        = number
  default     = 14
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
