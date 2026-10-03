variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "name_prefix" {
  type    = string
  default = "agent-space-ec2"
}

variable "instance_type" {
  type    = string
  default = "t3.xlarge"
}

variable "root_volume_gb" {
  type    = number
  default = 80
}
