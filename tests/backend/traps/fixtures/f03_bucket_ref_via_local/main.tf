# Red herring: fully protected, but the controls reference the bucket via a local.
resource "aws_s3_bucket" "data" {
  bucket = "acme-data"
}

locals {
  data_bucket_id = aws_s3_bucket.data.id
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = local.data_bucket_id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = local.data_bucket_id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = local.data_bucket_id
  versioning_configuration {
    status = "Enabled"
  }
}
