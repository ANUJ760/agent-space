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

variable "vnet_id" {
  description = "VNet ID for private DNS zone link"
  type        = string
}

variable "delegated_subnet_id" {
  description = "Subnet ID delegated to PostgreSQL Flexible Server"
  type        = string
}

variable "admin_username" {
  description = "Administrator username"
  type        = string
  default     = "agentspace_admin"
}

variable "admin_password" {
  description = "Administrator password (sensitive, provided by Key Vault module)"
  type        = string
  sensitive   = true
}

variable "sku_name" {
  description = "SKU for PostgreSQL Flexible Server"
  type        = string
  default     = "GP_Standard_D4s_v3"
}

variable "storage_mb" {
  description = "Max storage in MB"
  type        = number
  default     = 131072 # 128 GB
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
