
resource "aws_s3_bucket" "vendor_catalog" {
  bucket = "archibrief-p1-t1-vendor-catalog-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "vendor_catalog" {
  bucket = aws_s3_bucket.vendor_catalog.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "vendor_catalog" {
  bucket = aws_s3_bucket.vendor_catalog.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "vendor_catalog" {
  bucket = aws_s3_bucket.vendor_catalog.id
  depends_on = [aws_s3_bucket_versioning.vendor_catalog]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "vendor_catalog" {
  bucket = aws_s3_bucket.vendor_catalog.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.vendor_catalog.arn}",
          "${aws_s3_bucket.vendor_catalog.arn}/*"
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

resource "aws_s3_bucket" "shift_roster" {
  bucket = "archibrief-p1-t1-shift-roster-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "shift_roster" {
  bucket = aws_s3_bucket.shift_roster.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "shift_roster" {
  bucket = aws_s3_bucket.shift_roster.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "shift_roster" {
  bucket = aws_s3_bucket.shift_roster.id
  depends_on = [aws_s3_bucket_versioning.shift_roster]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "shift_roster" {
  bucket = aws_s3_bucket.shift_roster.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.shift_roster.arn}",
          "${aws_s3_bucket.shift_roster.arn}/*"
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

resource "aws_s3_bucket" "dispatch_summary" {
  bucket = "archibrief-p1-t1-dispatch-summary-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "dispatch_summary" {
  bucket = aws_s3_bucket.dispatch_summary.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "dispatch_summary" {
  bucket = aws_s3_bucket.dispatch_summary.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "dispatch_summary" {
  bucket = aws_s3_bucket.dispatch_summary.id
  depends_on = [aws_s3_bucket_versioning.dispatch_summary]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "dispatch_summary" {
  bucket = aws_s3_bucket.dispatch_summary.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.dispatch_summary.arn}",
          "${aws_s3_bucket.dispatch_summary.arn}/*"
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

resource "aws_s3_bucket" "inspection_index" {
  bucket = "archibrief-p1-t1-inspection-index-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "inspection_index" {
  bucket = aws_s3_bucket.inspection_index.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "inspection_index" {
  bucket = aws_s3_bucket.inspection_index.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "inspection_index" {
  bucket = aws_s3_bucket.inspection_index.id
  depends_on = [aws_s3_bucket_versioning.inspection_index]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "inspection_index" {
  bucket = aws_s3_bucket.inspection_index.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.inspection_index.arn}",
          "${aws_s3_bucket.inspection_index.arn}/*"
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

resource "aws_s3_bucket" "stock_snapshot" {
  bucket = "archibrief-p1-t1-stock-snapshot-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "stock_snapshot" {
  bucket = aws_s3_bucket.stock_snapshot.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "stock_snapshot" {
  bucket = aws_s3_bucket.stock_snapshot.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "stock_snapshot" {
  bucket = aws_s3_bucket.stock_snapshot.id
  depends_on = [aws_s3_bucket_versioning.stock_snapshot]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "stock_snapshot" {
  bucket = aws_s3_bucket.stock_snapshot.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.stock_snapshot.arn}",
          "${aws_s3_bucket.stock_snapshot.arn}/*"
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
