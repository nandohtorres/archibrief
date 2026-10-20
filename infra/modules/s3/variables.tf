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
  description = "The frontend's real origin (scheme + host), allowed to POST directly to this bucket via a presigned URL (ADR-0045's direct-upload flow). The bucket's CORS rule is separate from API Gateway's CORS and CloudFront's CSP."
}

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra origins allowed to POST uploads, e.g. the custom domain and www. Must match the API Gateway list, or uploads fail from those origins even though the API call succeeded."
}
