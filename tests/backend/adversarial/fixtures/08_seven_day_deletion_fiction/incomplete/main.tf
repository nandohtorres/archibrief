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

variable "uploads_bucket_lifecycle_days" {
  type = number
}

resource "aws_s3_bucket" "uploads" {
  bucket = "deletion-uploads"
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire"
    status = "Enabled"
    filter {}

    expiration {
      days = var.uploads_bucket_lifecycle_days
    }
  }
}
