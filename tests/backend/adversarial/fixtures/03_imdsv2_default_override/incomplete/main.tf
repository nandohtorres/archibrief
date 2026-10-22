# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# aws_ec2_instance_metadata_defaults is regional: it applies to the Region
# of its provider (or its own region argument). Values set on an instance at
# launch override account defaults (EC2 User Guide, "Order of precedence for
# instance metadata options").
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

provider "aws" {
  alias  = "west"
  region = "us-west-2"
}

# The account default comes from a variable with no default.
variable "imds_tokens" {
  type = string
}

resource "aws_ec2_instance_metadata_defaults" "east" {
  http_tokens = var.imds_tokens
}

resource "aws_iam_role" "proxy_role" {
  name = "proxy-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "proxy_s3_full" {
  role       = aws_iam_role.proxy_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_iam_instance_profile" "proxy" {
  name = "proxy"
  role = aws_iam_role.proxy_role.name
}

resource "aws_iam_role" "api_role" {
  name = "api-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "api" {
  name = "api"
  role = aws_iam_role.api_role.name
}

resource "aws_instance" "modern_api" {
  ami                  = "ami-0123456789abcdef0"
  instance_type        = "t3.micro"
  iam_instance_profile = aws_iam_instance_profile.api.name
  # Unset: depends on the account default, which is unknown here.
}
