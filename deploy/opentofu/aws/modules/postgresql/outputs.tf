output "db_instance_id" {
  description = "RDS DB Instance ID"
  value       = aws_db_instance.main.id
}

output "db_endpoint" {
  description = "Connection endpoint of PostgreSQL RDS"
  value       = aws_db_instance.main.endpoint
}

output "db_address" {
  description = "Hostname address of PostgreSQL RDS"
  value       = aws_db_instance.main.address
}

output "db_port" {
  description = "Port of PostgreSQL RDS"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.main.db_name
}

output "db_security_group_id" {
  description = "Security group ID for database access"
  value       = aws_security_group.db.id
}
