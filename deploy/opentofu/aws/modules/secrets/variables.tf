variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
