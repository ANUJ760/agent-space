variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
}

variable "location" {
  description = "Azure region for resource deployment"
  type        = string
  default     = "eastus2"
}

variable "name_prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "agent-space-prod"
}

variable "address_space" {
  description = "CIDR block for the Virtual Network"
  type        = list(string)
  default     = ["10.1.0.0/16"]
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
