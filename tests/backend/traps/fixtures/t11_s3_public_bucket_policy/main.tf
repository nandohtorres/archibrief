# Trap: "private" in the name, but a bucket policy grants GetObject to everyone.
resource "aws_s3_bucket" "private_customer_docs" {
  bucket = "acme-private-customer-docs"
}

resource "aws_s3_bucket_public_access_block" "private_customer_docs" {
  bucket                  = aws_s3_bucket.private_customer_docs.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "private_customer_docs" {
  bucket = aws_s3_bucket.private_customer_docs.id
  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::acme-private-customer-docs/*"}]
}
POLICY
}

resource "aws_s3_bucket_server_side_encryption_configuration" "private_customer_docs" {
  bucket = aws_s3_bucket.private_customer_docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "private_customer_docs" {
  bucket = aws_s3_bucket.private_customer_docs.id
  versioning_configuration {
    status = "Enabled"
  }
}
