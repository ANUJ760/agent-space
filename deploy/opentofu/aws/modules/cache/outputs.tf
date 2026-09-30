output "redis_primary_endpoint_address" {
  description = "Address of the primary Redis node"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "redis_port" {
  description = "Port of Redis cluster"
  value       = aws_elasticache_replication_group.main.port
}

output "redis_security_group_id" {
  description = "Security group ID for Redis access"
  value       = aws_security_group.redis.id
}
