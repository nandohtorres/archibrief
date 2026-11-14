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
  name = "p1-T1-maintenance"
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
  name = "p1-T1-maintenance"
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

resource "aws_iam_role" "contractor_export" {
  name = "p1-T1-contractor_export"
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

resource "aws_cloudwatch_log_group" "contractor_export" {
  name = "/aws/lambda/p1-T1-contractor_export"
  retention_in_days = 90
}

resource "aws_iam_role_policy" "contractor_export_logs" {
  name = "write-own-logs"
  role = aws_iam_role.contractor_export.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "${aws_cloudwatch_log_group.contractor_export.arn}:*"
      }
    ]
  })
}

resource "aws_lambda_function" "contractor_export" {
  function_name = "p1-T1-contractor_export"
  role = aws_iam_role.contractor_export.arn
  package_type = "Image"
  image_uri = "123456789012.dkr.ecr.us-east-2.amazonaws.com/p1-contractor_export@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  timeout = 30
  memory_size = 256
  reserved_concurrent_executions = 5
  depends_on = [aws_cloudwatch_log_group.contractor_export, aws_iam_role_policy.contractor_export_logs]
}

resource "aws_lambda_function_url" "contractor_export" {
  function_name = aws_lambda_function.contractor_export.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "contractor_export_url" {
  statement_id = "PublicUrl"
  action = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.contractor_export.function_name
  principal = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "contractor_export_invoke" {
  statement_id = "PublicInvokeViaUrl"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.contractor_export.function_name
  principal = "*"
  invoked_via_function_url = true
}

resource "aws_security_group" "internal_https" {
  name = "p1-internal-https"
  vpc_id = aws_vpc.workload.id
  ingress {
   from_port = 443
   to_port = 443
   protocol = "tcp"
   cidr_blocks = ["10.74.0.0/16"]
  }
}

resource "aws_cloudwatch_metric_alarm" "central_backlog" {
  alarm_name = "p1-T1-central_backlog"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 1
  metric_name = "ApproximateNumberOfMessagesVisible"
  namespace = "AWS/SQS"
  period = 300
  statistic = "Maximum"
  threshold = 0
  treat_missing_data = "notBreaching"
  dimensions = { QueueName = "central-observation-queue" }
  alarm_actions = ["arn:aws:sns:us-east-2:123456789012:central-operations"]
}
