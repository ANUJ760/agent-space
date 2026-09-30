output "log_group_arn" {
  description = "ARN of CloudWatch application log group"
  value       = aws_cloudwatch_log_group.app_logs.arn
}

output "log_group_name" {
  description = "Name of CloudWatch application log group"
  value       = aws_cloudwatch_log_group.app_logs.name
}

output "alerts_topic_arn" {
  description = "ARN of SNS topic for production alarms"
  value       = aws_sns_topic.alerts.arn
}
