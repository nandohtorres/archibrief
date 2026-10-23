# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# AWS Budgets notifications alert; they don't stop spending, and budget data
# lags billing by hours. An API Gateway usage plan quota only applies to
# requests that present an API key on methods with api_key_required = true.
# A Lambda function URL with authorization_type = "NONE" is a public entry
# point that CloudFront and WAF in front of API Gateway never see.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_role" "inference" {
  name = "inference"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Calls a paid model on every invocation.
resource "aws_lambda_function" "inference" {
  function_name = "inference"
  role          = aws_iam_role.inference.arn
  runtime       = "python3.12"
  handler       = "app.handler"
  filename      = "inference.zip"
  timeout       = 300

  environment {
    variables = {
      MODEL_ID = "anthropic.claude-sonnet"
    }
  }
}

resource "aws_api_gateway_rest_api" "llm" {
  name = "llm"
}

resource "aws_api_gateway_resource" "chat" {
  rest_api_id = aws_api_gateway_rest_api.llm.id
  parent_id   = aws_api_gateway_rest_api.llm.root_resource_id
  path_part   = "chat"
}

resource "aws_api_gateway_resource" "batch" {
  rest_api_id = aws_api_gateway_rest_api.llm.id
  parent_id   = aws_api_gateway_rest_api.llm.root_resource_id
  path_part   = "batch"
}

resource "aws_api_gateway_authorizer" "token" {
  name        = "token"
  rest_api_id = aws_api_gateway_rest_api.llm.id
  type        = "TOKEN"
  authorizer_uri = aws_lambda_function.inference.invoke_arn
}

resource "aws_api_gateway_method" "post_chat" {
  rest_api_id      = aws_api_gateway_rest_api.llm.id
  resource_id      = aws_api_gateway_resource.chat.id
  http_method      = "POST"
  authorization    = "CUSTOM"
  authorizer_id    = aws_api_gateway_authorizer.token.id
  api_key_required = false
}

resource "aws_api_gateway_method" "post_batch" {
  rest_api_id      = aws_api_gateway_rest_api.llm.id
  resource_id      = aws_api_gateway_resource.batch.id
  http_method      = "POST"
  authorization    = "NONE"

  api_key_required = false
}

resource "aws_api_gateway_deployment" "prod" {
  rest_api_id = aws_api_gateway_rest_api.llm.id
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.llm.id
  deployment_id = aws_api_gateway_deployment.prod.id
  stage_name    = "prod"
}

resource "aws_api_gateway_usage_plan" "free_tier" {
  name = "free-tier"

  api_stages {
    api_id = aws_api_gateway_rest_api.llm.id
    stage  = aws_api_gateway_stage.prod.stage_name
  }

  quota_settings {
    limit  = 100
    period = "DAY"
  }
}

resource "aws_wafv2_web_acl" "edge" {
  name  = "edge"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "edge"
    sampled_requests_enabled   = true
  }
}

resource "aws_cloudfront_distribution" "edge" {
  enabled    = true
  web_acl_id = aws_wafv2_web_acl.edge.arn

  origin {
    domain_name = "llm.execute-api.us-east-1.amazonaws.com"
    origin_id   = "api"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "api"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Notifies; does not stop spending.
resource "aws_budgets_budget" "monthly" {
  name         = "monthly"
  budget_type  = "COST"
  limit_amount = "50"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["ops@example.invalid"]
  }
}

resource "aws_sqs_queue" "jobs_dlq" {
  name = "jobs-dlq"
}

# Visibility timeout shorter than the function timeout means a message is
# redelivered while the first invocation is still running.
resource "aws_sqs_queue" "jobs" {
  name                       = "jobs"
  visibility_timeout_seconds = 30
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 1000
  })
}

resource "aws_lambda_event_source_mapping" "jobs" {
  event_source_arn = aws_sqs_queue.jobs.arn
  function_name    = aws_lambda_function.inference.arn
}

# A second public entry point that bypasses CloudFront, WAF and the authorizer.
resource "aws_lambda_function_url" "inference_direct" {
  function_name      = aws_lambda_function.inference.function_name
  authorization_type = "NONE"
}
