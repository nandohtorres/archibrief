# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# On a versioning-enabled bucket, lifecycle Expiration adds a delete marker
# and leaves the old version as noncurrent; only NoncurrentVersionExpiration
# removes it (S3 User Guide, "Expiring objects"), and removal can lag the
# expiry date. DynamoDB TTL deletes expired items "typically within a few
# days". A CloudWatch log group with retention_in_days unset (0) never
# expires. Step Functions Standard keeps execution history for 90 days.
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

resource "aws_s3_bucket" "uploads" {
  bucket = "deletion-uploads"
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire"
    status = "Enabled"
    filter {}

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }
}

resource "aws_s3_bucket" "uploads_replica" {
  bucket = "deletion-uploads-replica"
}

resource "aws_s3_bucket_public_access_block" "uploads_replica" {
  bucket                  = aws_s3_bucket.uploads_replica.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads_replica" {
  bucket = aws_s3_bucket.uploads_replica.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "uploads_replica" {
  bucket = aws_s3_bucket.uploads_replica.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads_replica" {
  bucket = aws_s3_bucket.uploads_replica.id

  rule {
    id     = "expire"
    status = "Enabled"
    filter {}

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }
}

resource "aws_dynamodb_table" "sessions" {
  name         = "sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  # Nothing in this code writes expires_at, so whether items expire is unknown.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name = "/app/api"
  retention_in_days = 7
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "pipeline"
  role_arn = "arn:aws:iam::123456789012:role/sfn"
  type     = "STANDARD"
  definition = jsonencode({
    StartAt = "Done"
    States  = { Done = { Type = "Succeed" } }
  })
}

resource "aws_backup_vault" "main" {
  name = "main"
}

resource "aws_backup_plan" "uploads" {
  name = "uploads"

  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 5 * * ? *)"

    lifecycle {
      delete_after = 7
    }
  }
}

resource "aws_backup_selection" "uploads" {
  name         = "uploads"
  plan_id      = aws_backup_plan.uploads.id
  iam_role_arn = "arn:aws:iam::123456789012:role/backup"
  resources    = [aws_s3_bucket.uploads.arn]
}
