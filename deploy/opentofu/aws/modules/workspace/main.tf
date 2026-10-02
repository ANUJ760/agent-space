resource "aws_security_group" "efs" {
  name        = "${var.name_prefix}-workspace-efs"
  description = "NFS access to the shared Agent Space workspace"
  vpc_id      = var.vpc_id

  ingress {
    description = "NFS from the application VPC"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-workspace-efs" })
}

resource "aws_efs_file_system" "workspace" {
  encrypted        = true
  kms_key_id       = var.kms_key_arn
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-workspace" })
}

resource "aws_efs_mount_target" "workspace" {
  # Subnet IDs are unknown until the VPC is created. Stable index keys let
  # OpenTofu determine the mount-target instances during the initial plan.
  for_each        = { for index, subnet_id in var.subnet_ids : tostring(index) => subnet_id }
  file_system_id  = aws_efs_file_system.workspace.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}
