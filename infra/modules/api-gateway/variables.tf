variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "state_machine_arn" {
  type = string
}

variable "domain_name" {
  type    = string
  default = "api.archibrief.dev"
}

# Was declared but never actually wired to a resource until Phase B
# (2026-10-14) — var.domain_name sat unused since this module's original
# build; Work-Project-Issues-Log.md, 2026-10-14 has the full story of
# how that was found. null keeps the API reachable only at its default
# *.execute-api.*.amazonaws.com endpoint (the pre-existing behavior),
# same null-means-off pairing as frontend-hosting's certificate_arn.
variable "certificate_arn" {
  type        = string
  default     = null
  description = "ACM certificate ARN, same region as this API (regional custom domain, not edge-optimized), covering var.domain_name. Leave null to skip creating the custom domain."
}

variable "frontend_origin" {
  type        = string
  description = "The frontend's real origin (scheme + host, e.g. https://d1t0c0ivnmhbnn.cloudfront.net) for CORS. Found 2026-10-12: this was hardcoded to the never-set-up https://archibrief.dev placeholder, so the browser's CORS preflight rejected every request from the real CloudFront origin with a generic 'Failed to fetch' — no request ever reached a Lambda."
}

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra allowed CORS origins alongside frontend_origin, e.g. [\"https://archibrief.dev\", \"https://www.archibrief.dev\"] once the custom domain resolves. Kept separate from frontend_origin rather than folded in, since frontend_origin is also used elsewhere as a single scalar (module docs/other references)."
}

variable "throttling_burst_limit" {
  type    = number
  default = 20
}

variable "throttling_rate_limit" {
  type    = number
  default = 10
}

# Deliberately separate, lower quota for the one public/unauthenticated
# route (GET /demo). Without this, demo_* and the admin-gated routes
# shared one stage-wide throttle bucket — a public traffic spike (or a
# bot hitting the one URL that needs no credential) could exhaust the
# whole API's quota and throttle real admin usage along with it. Each
# invocation of get_demo has ~zero marginal AWS cost on its own (it
# never touches DynamoDB/S3/Step Functions/AgentCore, per that route's
# own comment), so this exists purely to isolate blast radius between
# public and admin-gated traffic, not to cap spend.
variable "demo_throttling_burst_limit" {
  type    = number
  default = 5
}

variable "demo_throttling_rate_limit" {
  type    = number
  default = 2
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "admin_authorizer_zip_path" {
  type        = string
  description = "Deployment package for the pre-shared admin-credential Lambda authorizer (ADR-0044)."
}

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to every role this module creates and passes to lambda.amazonaws.com/apigateway.amazonaws.com — see modules/iam's runtime_permissions_boundary_arn output and Work-Project-Issues-Log.md, 2026-09-09."
}

variable "get_review_zip_path" {
  type        = string
  description = "Deployment package for GET /reviews/{reviewId}'s Lambda (backend/lambdas/get_review)."
}

variable "clarify_review_zip_path" {
  type        = string
  description = "Deployment package for POST /reviews/{reviewId}/clarify's Lambda (backend/lambdas/clarify_review)."
}

variable "reviews_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN) — get_review/clarify_review read it from REVIEWS_TABLE_NAME, same convention as the state-machine Lambdas in modules/step-functions-lambda."
}

variable "reviews_table_arn" {
  type        = string
  description = "DynamoDB table ARN, paired with reviews_table_name — scopes get_review's/clarify_review's IAM policies."
}

variable "deeper_review_zip_path" {
  type        = string
  description = "Deployment package for POST /reviews/{reviewId}/findings/{findingId}/deeper's Lambda (backend/lambdas/deeper_review)."
}

variable "findings_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN) — deeper_review writes each new versioned-child Finding here (first real writer of this table, 2026-10-01 — see Work-Project-Issues-Log.md)."
}

variable "findings_table_arn" {
  type        = string
  description = "DynamoDB table ARN, paired with findings_table_name — scopes deeper_review's IAM policy."
}

variable "reports_bucket_name" {
  type        = string
  description = "S3 bucket name (not ARN) — deeper_review reads the evidence ledger JSON from here via REPORTS_BUCKET_NAME."
}

variable "reports_bucket_arn" {
  type        = string
  description = "S3 bucket ARN, paired with reports_bucket_name — scopes deeper_review's IAM policy."
}

variable "agentcore_runtime_arn" {
  type        = string
  description = "ARN of the deployed AgentCore Runtime — deeper_review invokes it directly (bedrock-agentcore:InvokeAgentRuntime), bypassing Step Functions entirely (see backend/agent/graph.py's build_deeper_graph docstring). May be null before AgentCore is deployed, same deferral as modules/step-functions-lambda's own agentcore_runtime_arn."
  default     = null
}

variable "get_demo_zip_path" {
  type        = string
  description = "Deployment package for GET /demo's Lambda (backend/lambdas/get_demo) — fully static, bundles its own reference_report.json, no AWS clients at all."
}

variable "create_upload_zip_path" {
  type        = string
  description = "Deployment package for POST /uploads's Lambda (backend/lambdas/create_upload) — the direct-upload archive_path design (ADR-0045, drafted 2026-10-12)."
}
