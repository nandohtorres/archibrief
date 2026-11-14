terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 6.0, < 7.0" }
  }
}
provider "aws" { region = "us-east-2" }

resource "aws_vpc" "workload" {
  cidr_block = "10.74.0.0/16"
  enable_dns_support = true
  enable_dns_hostnames = true
}

resource "aws_subnet" "edge_a" {
  vpc_id = aws_vpc.workload.id
  cidr_block = "10.74.1.0/24"
  availability_zone = "us-east-2a"
  map_public_ip_on_launch = false
}

resource "aws_subnet" "app_a" {
  vpc_id = aws_vpc.workload.id
  cidr_block = "10.74.2.0/24"
  availability_zone = "us-east-2b"
  map_public_ip_on_launch = false
}

resource "aws_route_table" "app" {
  vpc_id = aws_vpc.workload.id
}

resource "aws_route_table_association" "edge_a" {
  subnet_id = aws_subnet.edge_a.id
  route_table_id = aws_route_table.app.id
}

resource "aws_route_table_association" "app_a" {
  subnet_id = aws_subnet.app_a.id
  route_table_id = aws_route_table.app.id
}

resource "aws_security_group" "database" {
  name = "p1-database"
  vpc_id = aws_vpc.workload.id
  ingress {
   from_port = 5432
   to_port = 5432
   protocol = "tcp"
   cidr_blocks = ["10.74.0.0/16"]
  }
}

resource "aws_db_subnet_group" "records" {
  name = "p1-records"
  subnet_ids = [aws_subnet.edge_a.id, aws_subnet.app_a.id]
}

resource "aws_db_instance" "records" {
  identifier = "p1-t2-records"
  engine = "postgres"
  instance_class = "db.t4g.small"
  allocated_storage = 30
  storage_type = "gp3"
  storage_encrypted = true
  username = "records_admin"
  manage_master_user_password = true
  db_subnet_group_name = aws_db_subnet_group.records.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible = false
  backup_retention_period = 0
  multi_az = false
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "p1-t2-records-final"
  auto_minor_version_upgrade = true
}

resource "aws_dynamodb_table" "journal" {
  name = "p1-T2-journal"
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "id"
  attribute {
   name = "id"
   type = "S"
  }
  point_in_time_recovery { enabled = false }
  server_side_encryption { enabled = true }
  deletion_protection_enabled = true
  ttl {
   attribute_name = "expires_at"
   enabled = false
  }
}

resource "aws_dynamodb_table" "sessions" {
  name = "p1-T2-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "id"
  attribute {
   name = "id"
   type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
  deletion_protection_enabled = true
  ttl {
   attribute_name = "expires_at"
   enabled = true
  }
}

resource "aws_s3_bucket" "evidence" {
  bucket = "archibrief-p1-t2-evidence-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Suspended" }
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  depends_on = [aws_s3_bucket_versioning.evidence]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 1 }
   noncurrent_version_expiration { noncurrent_days = 1 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.evidence.arn}",
          "${aws_s3_bucket.evidence.arn}/*"
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

resource "aws_sqs_queue" "ingest_failed" {
  name = "p1-T2-ingest-failed"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 60
}

resource "aws_sqs_queue" "ingest" {
  name = "p1-T2-ingest"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 345600
  visibility_timeout_seconds = 180
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.ingest_failed.arn, maxReceiveCount = 5 })
}

resource "aws_cloudwatch_metric_alarm" "ingest_failures" {
  alarm_name = "p1-T2-ingest_failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 1
  metric_name = "ApproximateNumberOfMessagesVisible"
  namespace = "AWS/SQS"
  period = 300
  statistic = "Maximum"
  threshold = 0
  treat_missing_data = "notBreaching"
  dimensions = { QueueName = aws_sqs_queue.ingest_failed.name }
  alarm_actions = ["arn:aws:sns:us-east-2:123456789012:central-operations"]
}

resource "aws_cloudwatch_log_group" "debug" {
  name = "/p1/T2/debug"
  retention_in_days = 0
}

resource "aws_cloudwatch_log_group" "audit" {
  name = "/p1/T2/audit"
  retention_in_days = 90
}

resource "aws_kms_key" "archive" {
  description = "Customer archive encryption"
  enable_key_rotation = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "archive" {
  name = "alias/p1-archive"
  target_key_id = aws_kms_key.archive.key_id
}

resource "aws_ebs_volume" "scratch" {
  availability_zone = "us-east-2b"
  size = 1000
  type = "io2"
  iops = 64000
  encrypted = true
  kms_key_id = aws_kms_key.archive.arn
  tags = { Purpose = "regenerable-scratch" }
}

resource "aws_ssm_parameter" "batch_size" {
  name = "/p1/records/batch-size"
  type = "String"
  value = "20"
}
