variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "postgresql_server_id" {
  description = "PostgreSQL Flexible Server ID for alert rules"
  type        = string
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
