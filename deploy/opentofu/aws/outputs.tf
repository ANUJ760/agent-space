# ==============================================================================
# Agent Space - AWS OpenTofu Outputs
# ==============================================================================
# Security requirement (Section 93): "Do not output secrets."
# Zero passwords, private keys, auth tokens, or plaintext credentials exported.
# ==============================================================================

output "vpc_id" {
  description = "VPC identifier"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "EKS cluster identifier"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "postgresql_endpoint" {
  description = "PostgreSQL RDS connection endpoint"
  value       = module.postgresql.db_endpoint
}

output "postgresql_database_name" {
  description = "PostgreSQL database name"
  value       = module.postgresql.db_name
}

output "storage_artifacts_bucket" {
  description = "S3 bucket for Content Addressable Storage artifacts"
  value       = module.storage.bucket_id
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint address"
  value       = module.cache.redis_primary_endpoint_address
}

output "events_queue_url" {
  description = "SQS primary event queue URL"
  value       = module.messaging.queue_url
}

output "gpu_node_group_id" {
  description = "EKS GPU managed node group identifier"
  value       = module.gpu.node_group_id
}

output "monitoring_log_group" {
  description = "CloudWatch log group for application and audit logs"
  value       = module.monitoring.log_group_name
}

output "monitoring_alerts_topic_arn" {
  description = "SNS topic ARN for operational alerts"
  value       = module.monitoring.alerts_topic_arn
}

output "kms_key_arn" {
  description = "Master KMS key ARN for infrastructure encryption"
  value       = module.secrets.kms_key_arn
}
