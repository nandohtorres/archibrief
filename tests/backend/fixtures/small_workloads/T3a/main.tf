terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 6.0, < 7.0" }
  }
}
provider "aws" { region = "eu-west-1" }

resource "aws_vpc" "workload" {
  cidr_block = "10.74.0.0/16"
  enable_dns_support = true
  enable_dns_hostnames = true
}

resource "aws_subnet" "edge_a" {
  vpc_id = aws_vpc.workload.id
  cidr_block = "10.74.1.0/24"
  availability_zone = "eu-west-1a"
  map_public_ip_on_launch = false
}

resource "aws_subnet" "app_a" {
  vpc_id = aws_vpc.workload.id
  cidr_block = "10.74.2.0/24"
  availability_zone = "eu-west-1b"
  map_public_ip_on_launch = false
}

resource "aws_internet_gateway" "edge" {
  vpc_id = aws_vpc.workload.id
}

resource "aws_route_table" "edge" {
  vpc_id = aws_vpc.workload.id
  route {
   cidr_block = "0.0.0.0/0"
   gateway_id = aws_internet_gateway.edge.id
  }
}

resource "aws_route_table" "app" {
  vpc_id = aws_vpc.workload.id
  route {
   cidr_block = "0.0.0.0/0"
   gateway_id = aws_internet_gateway.edge.id
  }
}

resource "aws_route_table_association" "edge_a" {
  subnet_id = aws_subnet.edge_a.id
  route_table_id = aws_route_table.edge.id
}

resource "aws_route_table_association" "app_a" {
  subnet_id = aws_subnet.app_a.id
  route_table_id = aws_route_table.app.id
}

resource "aws_security_group" "maintenance" {
  name = "p1-maintenance"
  vpc_id = aws_vpc.workload.id
  ingress {
   from_port = 22
   to_port = 22
   protocol = "tcp"
   cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
   from_port = 443
   to_port = 443
   protocol = "tcp"
   cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "spare" {
  name = "p1-spare-maintenance"
  vpc_id = aws_vpc.workload.id
  ingress {
   from_port = 3389
   to_port = 3389
   protocol = "tcp"
   cidr_blocks = ["10.74.0.0/16"]
  }
}

resource "aws_ebs_encryption_by_default" "regional" {
  enabled = true
}

resource "aws_iam_role" "maintenance" {
  name = "p1-T3a-maintenance"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "ec2.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "maintenance" {
  role = aws_iam_role.maintenance.name
}

resource "aws_iam_policy" "maintenance" {
  name = "p1-T3a-maintenance"
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "*",
        "Resource": "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "maintenance" {
  role = aws_iam_role.maintenance.name
  policy_arn = aws_iam_policy.maintenance.arn
}

resource "aws_instance" "maintenance" {
  ami = "ami-0123456789abcdef0"
  instance_type = "t3.small"
  subnet_id = aws_subnet.app_a.id
  associate_public_ip_address = true
  vpc_security_group_ids = [aws_security_group.maintenance.id]
  iam_instance_profile = aws_iam_instance_profile.maintenance.name
  metadata_options {
   http_endpoint = "enabled"
   http_tokens = "optional"
  }
  root_block_device {
   volume_type = "gp3"
   volume_size = 30
   encrypted = true
  }
  tags = { Name = "maintenance-worker" }
}

resource "aws_iam_role" "dispatch" {
  name = "p1-T3a-dispatch"
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

resource "aws_cloudwatch_log_group" "dispatch" {
  name = "/aws/lambda/p1-T3a-dispatch"
  retention_in_days = 90
}

resource "aws_iam_role_policy" "dispatch_logs" {
  name = "write-own-logs"
  role = aws_iam_role.dispatch.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "${aws_cloudwatch_log_group.dispatch.arn}:*"
      }
    ]
  })
}

resource "aws_lambda_function" "dispatch" {
  function_name = "p1-T3a-dispatch"
  role = aws_iam_role.dispatch.arn
  package_type = "Image"
  image_uri = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/p1-dispatch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  timeout = 30
  memory_size = 256
  reserved_concurrent_executions = 5
  depends_on = [aws_cloudwatch_log_group.dispatch, aws_iam_role_policy.dispatch_logs]
}

resource "aws_lambda_function_url" "dispatch" {
  function_name = aws_lambda_function.dispatch.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "dispatch_url" {
  statement_id = "PublicUrl"
  action = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.dispatch.function_name
  principal = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "dispatch_invoke" {
  statement_id = "PublicInvokeViaUrl"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatch.function_name
  principal = "*"
  invoked_via_function_url = true
}

resource "aws_apigatewayv2_api" "dispatch" {
  name = "dispatch-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "dispatch" {
  api_id = aws_apigatewayv2_api.dispatch.id
  integration_type = "AWS_PROXY"
  integration_uri = aws_lambda_function.dispatch.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_authorizer" "staff" {
  api_id = aws_apigatewayv2_api.dispatch.id
  name = "staff-jwt"
  authorizer_type = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
   audience = ["dispatch-staff"]
   issuer = "https://identity.example.com/dispatch"
  }
}

resource "aws_apigatewayv2_route" "read" {
  api_id = aws_apigatewayv2_api.dispatch.id
  route_key = "GET /dispatch"
  target = "integrations/${aws_apigatewayv2_integration.dispatch.id}"
  authorization_type = "JWT"
  authorizer_id = aws_apigatewayv2_authorizer.staff.id
  authorization_scopes = ["dispatch.read"]
}

resource "aws_apigatewayv2_route" "override" {
  api_id = aws_apigatewayv2_api.dispatch.id
  route_key = "POST /dispatch/override"
  target = "integrations/${aws_apigatewayv2_integration.dispatch.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_stage" "live" {
  api_id = aws_apigatewayv2_api.dispatch.id
  name = "$default"
  auto_deploy = true
  access_log_settings {
   destination_arn = aws_cloudwatch_log_group.gateway.arn
   format = jsonencode({ requestId = "$context.requestId", status = "$context.status", routeKey = "$context.routeKey" })
  }
  default_route_settings {
   throttling_burst_limit = 20
   throttling_rate_limit = 10
  }
}

resource "aws_lambda_permission" "gateway" {
  statement_id = "DispatchGateway"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatch.function_name
  principal = "apigateway.amazonaws.com"
  source_arn = "${aws_apigatewayv2_api.dispatch.execution_arn}/*/*"
  source_account = "123456789012"
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
  identifier = "p1-t3a-records"
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
  final_snapshot_identifier = "p1-t3a-records-final"
  auto_minor_version_upgrade = true
}

resource "aws_dynamodb_table" "journal" {
  name = "p1-T3a-journal"
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

provider "aws" {
 alias = "archive_us"
 region = "us-east-2"
}

resource "aws_s3_bucket" "evidence" {
  provider = aws.archive_us
  bucket = "archibrief-p1-t3a-evidence-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  provider = aws.archive_us
  bucket = aws_s3_bucket.evidence.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  provider = aws.archive_us
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  provider = aws.archive_us
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
  provider = aws.archive_us
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
  name = "p1-T3a-ingest-failed"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 60
}

resource "aws_sqs_queue" "ingest" {
  name = "p1-T3a-ingest"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 345600
  visibility_timeout_seconds = 180
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.ingest_failed.arn, maxReceiveCount = 5 })
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

resource "aws_cloudwatch_log_group" "debug" {
  name = "/p1/T3a/debug"
  retention_in_days = 0
}

resource "aws_cloudwatch_log_group" "audit" {
  name = "/p1/T3a/audit"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "gateway" {
  name = "/p1/T3a/gateway"
  retention_in_days = 90
}

resource "aws_ebs_volume" "scratch" {
  availability_zone = "eu-west-1b"
  size = 1000
  type = "io2"
  iops = 64000
  encrypted = true
  kms_key_id = aws_kms_key.archive.arn
  tags = { Purpose = "regenerable-scratch" }
}

resource "aws_sns_topic" "dispatch_alerts" {
  name = "p1-dispatch-alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_cloudwatch_metric_alarm" "ingest_failures" {
  alarm_name = "p1-T3a-ingest_failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 1
  metric_name = "ApproximateNumberOfMessagesVisible"
  namespace = "AWS/SQS"
  period = 300
  statistic = "Maximum"
  threshold = 0
  treat_missing_data = "notBreaching"
  dimensions = { QueueName = aws_sqs_queue.ingest_failed.name }
  alarm_actions = ["arn:aws:sns:eu-west-1:123456789012:central-operations"]
}

resource "aws_ssm_parameter" "dispatch_mode" {
  name = "/p1/dispatch/mode"
  type = "String"
  value = "staff-only"
}
