# Red herring: this bucket is never created (count = 0).
resource "aws_s3_bucket" "legacy_archive" {
  count  = 0
  bucket = "acme-legacy-archive"
}
