variable "location" {
  description = "Target Azure deployment region"
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
  default     = "rg-agentspace-prod"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "name_prefix" {
  description = "Prefix prepended to all resource names"
  type        = string
  default     = "agent-space-prod"
}

variable "tags" {
  description = "Global tags applied to all Azure resources"
  type        = map(string)
  default = {
    Project     = "AgentSpace"
    Environment = "production"
    ManagedBy   = "OpenTofu"
  }
}
