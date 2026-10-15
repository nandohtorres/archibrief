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

# ADR-0045's direct-upload flow has the browser POST straight to this
# bucket via a presigned URL (create_upload's generate_presigned_post) —
# that still needs the bucket's own CORS configuration, separate from
# and in addition to API Gateway's CORS and CloudFront's CSP, both of
# which were fixed first without this one (found 2026-10-12: the browser
# got as far as attempting the real cross-origin POST and only then hit
# "No 'Access-Control-Allow-Origin' header is present").
resource "aws_s3_bucket_cors_configuration" "source_of_truth" {
  bucket = aws_s3_bucket.source_of_truth.id

  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = [var.frontend_origin]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}
