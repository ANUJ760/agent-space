variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "kms_key_arn" {
  description = "KMS Key ARN for message encryption"
  type        = string
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
