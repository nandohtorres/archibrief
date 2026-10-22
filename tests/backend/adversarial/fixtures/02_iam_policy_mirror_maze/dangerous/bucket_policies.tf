resource "aws_s3_bucket" "reports" {
  bucket = "maze-reports"
}

resource "aws_s3_bucket" "exports" {
  bucket = "maze-exports"
}

resource "aws_s3_bucket" "media" {
  bucket = "maze-media"
}

# Restrictive condition, literal policy: only requests through one VPC endpoint.
resource "aws_s3_bucket_policy" "reports_vpce_json" {
  bucket = aws_s3_bucket.reports.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::maze-reports/*"
      Condition = { StringEquals = { "aws:SourceVpce" = "vpce-1a2b3c4d" } }
    }]
  })
}

# The same restriction written as an aws_iam_policy_document.
data "aws_iam_policy_document" "exports_vpce" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::maze-exports/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpce"
      values   = ["vpce-1a2b3c4d"]
    }
  }
}

resource "aws_s3_bucket_policy" "exports_vpce_document" {
  bucket = aws_s3_bucket.exports.id
  policy = data.aws_iam_policy_document.exports_vpce.json
}

# Irrelevant condition: requiring HTTPS still lets anyone on the internet read.
resource "aws_s3_bucket_policy" "media_https_only" {
  bucket = aws_s3_bucket.media.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::maze-media/*"
      Condition = { Bool = { "aws:SecureTransport" = "true" } }
    }]
  })
}
