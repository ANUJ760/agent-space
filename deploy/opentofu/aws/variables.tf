variable "aws_region" {
  description = "Target AWS deployment region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "production"
}

variable "name_prefix" {
  description = "Prefix prepended to all resource names"
  type        = string
  default     = "agent-space-prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to span"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "tags" {
  description = "Global tags applied to all infrastructure components"
  type        = map(string)
  default = {
    Project     = "AgentSpace"
    Environment = "production"
    ManagedBy   = "OpenTofu"
  }
}
