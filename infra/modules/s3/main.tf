# Terraform module: s3
# Ordinary S3 — the immutable source of truth for normalized documents,
# submitted archives, and generated reports (ADR-0007, ADR-0042).
# Distinct from infra/modules/s3-vectors, which is a rebuildable index
# built on top of this bucket, not the source of truth itself.

resource "aws_s3_bucket" "source_of_truth" {
  bucket = var.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "source_of_truth" {
  bucket = aws_s3_bucket.source_of_truth.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "source_of_truth" {
  bucket = aws_s3_bucket.source_of_truth.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "source_of_truth" {
  bucket                  = aws_s3_bucket.source_of_truth.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
