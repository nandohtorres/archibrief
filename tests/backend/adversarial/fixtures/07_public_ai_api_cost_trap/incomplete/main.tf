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

# Who can invoke the URL is decided by a variable with no default.
variable "url_auth" {
  type = string
}

resource "aws_lambda_function_url" "inference_direct" {
  function_name      = aws_lambda_function.inference.function_name
  authorization_type = var.url_auth
}
