# Master KMS Key for AgentSpace encryption across EKS, RDS, S3, SQS, Secrets
resource "aws_kms_key" "main" {
  description             = "KMS Key for ${var.name_prefix} infrastructure encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-kms-key"
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.main.key_id
}

# Cryptographically Secure Random Passwords
resource "random_password" "db_password" {
  length  = 32
  special = false # Avoid shell/URI escaping issues in database URLs
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "random_password" "session_secret" {
  length  = 64
  special = false
}

# AWS Secrets Manager Secret container
resource "aws_secretsmanager_secret" "app_secrets" {
  name        = "${var.name_prefix}/app-secrets"
  description = "Enterprise runtime credentials for AgentSpace application"
  kms_key_id  = aws_kms_key.main.arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-app-secrets"
  })
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    DATABASE_PASSWORD      = random_password.db_password.result
    REDIS_AUTH_TOKEN       = random_password.redis_auth.result
    SESSION_SIGNING_KEY    = random_password.session_secret.result
    OPENAI_API_KEY         = "managed-externally"
    ANTHROPIC_API_KEY      = "managed-externally"
    KEYCLOAK_CLIENT_SECRET = "managed-externally"
  })
}
