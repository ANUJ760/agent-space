output "kms_key_arn" {
  description = "ARN of the master KMS key"
  value       = aws_kms_key.main.arn
}

output "secrets_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

output "secrets_name" {
  description = "Name of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.app_secrets.name
}

output "default_gemini_api_key_secret_name" {
  description = "Name of the separately managed default Gemini API key secret"
  value       = aws_secretsmanager_secret.default_gemini_api_key.name
}

# Passwords provided only for direct module composition (marked sensitive)
output "db_password" {
  description = "Database master password for RDS module instantiation"
  value       = random_password.db_password.result
  sensitive   = true
}

output "redis_auth_token" {
  description = "Redis AUTH token for ElastiCache module instantiation"
  value       = random_password.redis_auth.result
  sensitive   = true
}
