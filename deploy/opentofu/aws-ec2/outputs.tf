output "instance_id" {
  value = aws_instance.app.id
}

output "public_ip" {
  value = aws_eip.app.public_ip
}

output "ssm_connect_command" {
  value = "aws ssm start-session --region ${var.aws_region} --target ${aws_instance.app.id}"
}

output "runtime_env_secret_name" {
  value = aws_secretsmanager_secret.runtime_env.name
}
