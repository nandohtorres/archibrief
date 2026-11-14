terraform {
  required_providers { aws = { source = "hashicorp/aws" } }
}
variable "lane" { type = string }
variable "pitr_enabled" { type = bool }
variable "failed_retention" { type = number }

resource "aws_sqs_queue" "failed" {
  name = "p1-${var.lane}-failed"
  sqs_managed_sse_enabled = true
  message_retention_seconds = var.failed_retention
}

resource "aws_sqs_queue" "incoming" {
  name = "p1-${var.lane}-incoming"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 345600
  visibility_timeout_seconds = 180
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.failed.arn, maxReceiveCount = 5 })
}

resource "aws_cloudwatch_metric_alarm" "failed" {
  alarm_name = "p1-${var.lane}-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 1
  metric_name = "ApproximateNumberOfMessagesVisible"
  namespace = "AWS/SQS"
  period = 300
  statistic = "Maximum"
  threshold = 0
  treat_missing_data = "notBreaching"
  dimensions = { QueueName = aws_sqs_queue.failed.name }
  alarm_actions = ["arn:aws:sns:us-east-2:123456789012:central-operations"]
}

resource "aws_dynamodb_table" "receipts" {
  name = "p1-${var.lane}-receipts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "id"
  attribute {
   name = "id"
   type = "S"
  }
  point_in_time_recovery { enabled = var.pitr_enabled }
  server_side_encryption { enabled = true }
  deletion_protection_enabled = true
}

resource "aws_s3_bucket" "payloads" {
  bucket = "archibrief-p1-${var.lane}-payloads-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "payloads" {
  bucket = aws_s3_bucket.payloads.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "payloads" {
  bucket = aws_s3_bucket.payloads.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "payloads" {
  bucket = aws_s3_bucket.payloads.id
  depends_on = [aws_s3_bucket_versioning.payloads]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "payloads" {
  bucket = aws_s3_bucket.payloads.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.payloads.arn}",
          "${aws_s3_bucket.payloads.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role" "consumer" {
  name = "p1-${var.lane}-consumer"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "consumer" {
  name = "/aws/lambda/p1-${var.lane}-consumer"
  retention_in_days = 90
}

resource "aws_iam_role_policy" "consumer" {
  name = "consume-own-lane"
  role = aws_iam_role.consumer.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        "Resource": "${aws_sqs_queue.incoming.arn}"
      },
      {
        "Effect": "Allow",
        "Action": [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ],
        "Resource": "${aws_dynamodb_table.receipts.arn}"
      },
      {
        "Effect": "Allow",
        "Action": [
          "s3:GetObject",
          "s3:PutObject"
        ],
        "Resource": "${aws_s3_bucket.payloads.arn}/*"
      },
      {
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "${aws_cloudwatch_log_group.consumer.arn}:*"
      }
    ]
  })
}

resource "aws_lambda_function" "consumer" {
  function_name = "p1-${var.lane}-consumer"
  role = aws_iam_role.consumer.arn
  package_type = "Image"
  image_uri = "123456789012.dkr.ecr.us-east-2.amazonaws.com/lane-consumer@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  timeout = 30
  memory_size = 256
  reserved_concurrent_executions = 5
  depends_on = [aws_iam_role_policy.consumer, aws_cloudwatch_log_group.consumer]
}

resource "aws_lambda_event_source_mapping" "incoming" {
  event_source_arn = aws_sqs_queue.incoming.arn
  function_name = aws_lambda_function.consumer.arn
  batch_size = 10
  function_response_types = ["ReportBatchItemFailures"]
  depends_on = [aws_iam_role_policy.consumer]
}

resource "aws_ssm_parameter" "lane_name" {
  name = "/p1/${var.lane}/name"
  type = "String"
  value = var.lane
}
