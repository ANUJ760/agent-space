output "queue_url" {
  description = "URL of primary SQS event queue"
  value       = aws_sqs_queue.events.url
}

output "queue_arn" {
  description = "ARN of primary SQS event queue"
  value       = aws_sqs_queue.events.arn
}

output "dlq_arn" {
  description = "ARN of Dead Letter Queue"
  value       = aws_sqs_queue.events_dlq.arn
}

output "topic_arn" {
  description = "ARN of SNS events topic"
  value       = aws_sns_topic.events.arn
}
