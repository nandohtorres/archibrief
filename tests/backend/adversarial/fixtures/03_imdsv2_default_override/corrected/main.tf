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

# Account default for us-east-1 only.
resource "aws_ec2_instance_metadata_defaults" "east" {
  http_tokens                 = "required"
  http_put_response_hop_limit = 2
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

resource "aws_instance" "legacy_proxy" {
  ami                  = "ami-0123456789abcdef0"
  instance_type        = "t3.micro"
  iam_instance_profile = aws_iam_instance_profile.proxy.name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }
}

resource "aws_instance" "modern_api" {
  ami                  = "ami-0123456789abcdef0"
  instance_type        = "t3.micro"
  iam_instance_profile = aws_iam_instance_profile.api.name
  # Unset: takes the us-east-1 account default (required).
}

resource "aws_instance" "sealed_batch" {
  ami                  = "ami-0123456789abcdef0"
  instance_type        = "t3.micro"
  iam_instance_profile = aws_iam_instance_profile.api.name

  metadata_options {
    http_endpoint = "disabled"
  }
}
