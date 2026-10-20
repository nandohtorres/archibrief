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

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra origins allowed to POST uploads, e.g. the custom domain and www. Must match the API Gateway list, or uploads fail from those origins even though the API call succeeded (Codex F03)."
}
