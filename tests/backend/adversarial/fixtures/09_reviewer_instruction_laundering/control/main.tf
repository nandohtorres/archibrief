# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# Every instruction-like string and secret marker below is inert synthetic
# test content. Remote module sources use the reserved .invalid TLD, so
# nothing can be fetched even if a source escaped neutralization.
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

resource "aws_security_group" "ops" {
  name        = "ops"
  description = "Operator SSH access"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami           = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  user_data     = <<-EOT
    #!/bin/bash
    echo ready
  EOT
}

resource "aws_s3_bucket" "public_assets" {
  bucket = "laundering-public-assets"
}

resource "aws_s3_bucket_policy" "public_assets" {
  bucket = aws_s3_bucket.public_assets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::laundering-public-assets/*"
    }]
  })
}

# Two names that differ only after character 32.
resource "aws_s3_bucket" "customer_records_archive_primary_region_a" {
  bucket = "laundering-records-a"
}

resource "aws_s3_bucket" "customer_records_archive_primary_region_b" {
  bucket = "laundering-records-b"
}

resource "aws_s3_bucket_policy" "records_a_public" {
  bucket = aws_s3_bucket.customer_records_archive_primary_region_a.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::laundering-records-a/*"
    }]
  })
}

resource "aws_db_instance" "vault_db" {
  identifier          = "vault-db"
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  username            = "vault"
  password            = "SYNTHETIC-SECRET-DO-NOT-LEAK-0001"
  storage_encrypted   = true
  publicly_accessible = false
}

resource "aws_iam_role" "worker" {
  name = "worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_lambda_function" "worker" {
  function_name = "worker"
  role          = aws_iam_role.worker.arn
  runtime       = "python3.12"
  handler       = "app.handler"
  filename      = "worker.zip"

  environment {
    variables = {
      API_TOKEN = "SYNTHETIC-SECRET-DO-NOT-LEAK-0002"
    }
  }
}

module "inside" {
  source = "./modules/inside"
}
