variable "bucket_name" {
  type        = string
  description = "Name of the immutable source-of-truth bucket (ADR-0007/0042)."
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "frontend_origin" {
  type        = string
  description = "The frontend's real origin (scheme + host), allowed to POST directly to this bucket via a presigned URL (ADR-0045's direct-upload flow). Found 2026-10-12: CSP/CORS on API Gateway and CloudFront were fixed first, but the bucket itself had no CORS configuration at all, so the browser's own presigned-POST request was rejected independently of either of those."
}
