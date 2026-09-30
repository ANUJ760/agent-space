# Dead Letter Queue
resource "aws_sqs_queue" "events_dlq" {
  name                      = "${var.name_prefix}-events-dlq"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = var.kms_key_arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-events-dlq"
  })
}

# Primary Event Queue with Redrive Policy
resource "aws_sqs_queue" "events" {
  name                      = "${var.name_prefix}-events-queue"
  message_retention_seconds = 345600 # 4 days
  visibility_timeout_seconds = 300
  kms_master_key_id         = var.kms_key_arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = 3
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-events-queue"
  })
}

# SNS Event Notification Topic
resource "aws_sns_topic" "events" {
  name              = "${var.name_prefix}-events-topic"
  kms_master_key_id = var.kms_key_arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-events-topic"
  })
}

# SNS to SQS subscription
resource "aws_sns_topic_subscription" "events_queue" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.events.arn
}
