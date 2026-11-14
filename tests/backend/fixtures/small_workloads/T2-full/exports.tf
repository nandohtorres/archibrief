
resource "aws_s3_bucket" "monthly_rollup" {
  bucket = "archibrief-p1-t2-monthly-rollup-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "monthly_rollup" {
  bucket = aws_s3_bucket.monthly_rollup.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "monthly_rollup" {
  bucket = aws_s3_bucket.monthly_rollup.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "monthly_rollup" {
  bucket = aws_s3_bucket.monthly_rollup.id
  depends_on = [aws_s3_bucket_versioning.monthly_rollup]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "monthly_rollup" {
  bucket = aws_s3_bucket.monthly_rollup.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.monthly_rollup.arn}",
          "${aws_s3_bucket.monthly_rollup.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket" "vendor_statement" {
  bucket = "archibrief-p1-t2-vendor-statement-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "vendor_statement" {
  bucket = aws_s3_bucket.vendor_statement.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "vendor_statement" {
  bucket = aws_s3_bucket.vendor_statement.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "vendor_statement" {
  bucket = aws_s3_bucket.vendor_statement.id
  depends_on = [aws_s3_bucket_versioning.vendor_statement]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "vendor_statement" {
  bucket = aws_s3_bucket.vendor_statement.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.vendor_statement.arn}",
          "${aws_s3_bucket.vendor_statement.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket" "capacity_forecast" {
  bucket = "archibrief-p1-t2-capacity-forecast-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "capacity_forecast" {
  bucket = aws_s3_bucket.capacity_forecast.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "capacity_forecast" {
  bucket = aws_s3_bucket.capacity_forecast.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "capacity_forecast" {
  bucket = aws_s3_bucket.capacity_forecast.id
  depends_on = [aws_s3_bucket_versioning.capacity_forecast]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "capacity_forecast" {
  bucket = aws_s3_bucket.capacity_forecast.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.capacity_forecast.arn}",
          "${aws_s3_bucket.capacity_forecast.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket" "route_scorecard" {
  bucket = "archibrief-p1-t2-route-scorecard-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "route_scorecard" {
  bucket = aws_s3_bucket.route_scorecard.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "route_scorecard" {
  bucket = aws_s3_bucket.route_scorecard.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "route_scorecard" {
  bucket = aws_s3_bucket.route_scorecard.id
  depends_on = [aws_s3_bucket_versioning.route_scorecard]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "route_scorecard" {
  bucket = aws_s3_bucket.route_scorecard.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.route_scorecard.arn}",
          "${aws_s3_bucket.route_scorecard.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket" "inventory_digest" {
  bucket = "archibrief-p1-t2-inventory-digest-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "inventory_digest" {
  bucket = aws_s3_bucket.inventory_digest.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "inventory_digest" {
  bucket = aws_s3_bucket.inventory_digest.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "inventory_digest" {
  bucket = aws_s3_bucket.inventory_digest.id
  depends_on = [aws_s3_bucket_versioning.inventory_digest]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "inventory_digest" {
  bucket = aws_s3_bucket.inventory_digest.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.inventory_digest.arn}",
          "${aws_s3_bucket.inventory_digest.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}
