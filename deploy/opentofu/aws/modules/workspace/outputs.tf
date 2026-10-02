output "file_system_id" {
  value       = aws_efs_file_system.workspace.id
  description = "EFS file system used by collaborative workspaces"
}
