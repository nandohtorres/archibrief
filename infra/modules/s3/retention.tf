# Asynchronous cleanup of user-data prefixes only. Normalized corpus content
# is deliberately outside these rules. This is not exact seven-day deletion:
# S3 ages current and noncurrent versions separately and schedules cleanup.
resource "aws_s3_bucket_lifecycle_configuration" "user_data" {
  bucket = aws_s3_bucket.source_of_truth.id

  depends_on = [aws_s3_bucket_versioning.source_of_truth]

  dynamic "rule" {
    for_each = toset(["uploads/", "parsed/", "reports/"])
    content {
      id     = "expire-${trimsuffix(rule.value, "/")}"
      status = "Enabled"

      filter {
        prefix = rule.value
      }

      expiration {
        days = 7
      }

      noncurrent_version_expiration {
        noncurrent_days = 1
      }

      abort_incomplete_multipart_upload {
        days_after_initiation = 1
      }
    }
  }
}
