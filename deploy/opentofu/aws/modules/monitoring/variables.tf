variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "kms_key_arn" {
  description = "KMS Key ARN for CloudWatch Log Group encryption"
  type        = string
}

variable "db_instance_id" {
  description = "RDS DB Instance ID for monitoring alarms"
  type        = string
}

variable "redis_replication_group_id" {
  description = "ElastiCache replication group ID for monitoring alarms"
  type        = string
}

variable "retention_in_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 90
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
