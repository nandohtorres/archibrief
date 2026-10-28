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

# null keeps the API reachable only at its default
# *.execute-api.*.amazonaws.com endpoint, the same null-means-off pattern
# as frontend-hosting's certificate_arn.
variable "certificate_arn" {
  type        = string
  default     = null
  description = "ACM certificate ARN, same region as this API (regional custom domain, not edge-optimized), covering var.domain_name. Leave null to skip creating the custom domain."
}

variable "frontend_origin" {
  type        = string
  description = "The frontend's real origin (scheme + host, e.g. https://dxxxxxxxxxxxxx.cloudfront.net) for CORS. If it doesn't match the origin the browser uses, the CORS preflight rejects every request with a generic 'Failed to fetch' before any Lambda runs."
}

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra allowed CORS origins alongside frontend_origin, e.g. [\"https://archibrief.dev\", \"https://www.archibrief.dev\"] once the custom domain resolves. Separate because frontend_origin is used elsewhere as a single scalar."
}

variable "throttling_burst_limit" {
  type    = number
  default = 20
}

variable "throttling_rate_limit" {
  type    = number
  default = 10
}

# Separate, lower quota for GET /demo, so a bot hitting that one free URL
# can't use up the stage-wide quota everyone else shares. get_demo has
# near-zero marginal cost, so this isolates blast radius rather than
# capping spend.
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

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to every role this module creates and passes to lambda.amazonaws.com/apigateway.amazonaws.com (modules/iam's runtime_permissions_boundary_arn output)."
}

variable "get_review_zip_path" {
  type        = string
  description = "Deployment package for GET /reviews/{reviewId}'s Lambda (backend/lambdas/get_review)."
}

variable "reviews_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN); get_review reads it from REVIEWS_TABLE_NAME."
}

variable "reviews_table_arn" {
  type        = string
  description = "DynamoDB table ARN, paired with reviews_table_name; scopes get_review's IAM policy."
}

variable "deeper_review_zip_path" {
  type        = string
  description = "Deployment package for POST /reviews/{reviewId}/findings/{findingId}/deeper's Lambda (backend/lambdas/deeper_review)."
}

variable "findings_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN); deeper_review writes each new versioned-child Finding here."
}

variable "findings_table_arn" {
  type        = string
  description = "DynamoDB table ARN, paired with findings_table_name; scopes deeper_review's IAM policy."
}

variable "reports_bucket_name" {
  type        = string
  description = "S3 bucket name (not ARN); deeper_review reads the evidence ledger JSON from here via REPORTS_BUCKET_NAME."
}

variable "reports_bucket_arn" {
  type        = string
  description = "S3 bucket ARN, paired with reports_bucket_name; scopes deeper_review's IAM policy."
}

variable "agentcore_runtime_arn" {
  type        = string
  description = "ARN of the deployed AgentCore Runtime. deeper_review invokes it directly (bedrock-agentcore:InvokeAgentRuntime), bypassing Step Functions (see backend/agent/graph.py's build_deeper_graph docstring). May be null before AgentCore is deployed, like modules/step-functions-lambda's agentcore_runtime_arn."
  default     = null
}

variable "get_demo_zip_path" {
  type        = string
  description = "Deployment package for GET /demo's Lambda (backend/lambdas/get_demo); fully static, bundles its own reference_report.json, no AWS clients."
}

variable "create_upload_zip_path" {
  type        = string
  description = "Deployment package for POST /uploads's Lambda (backend/lambdas/create_upload), the direct-upload design (ADR-0045)."
}

variable "kill_switch_parameter_name" {
  type        = string
  description = "SSM parameter holding the ADR-0030 kill switch; the deeper Lambda refuses paid work when it reads \"true\" or can't be read."
}

variable "kill_switch_parameter_arn" {
  type = string
}

# --- Report chat (ADR-0050) ----------------------------------------------

variable "ask_question_zip_path" {
  type        = string
  description = "Deployment package for POST /reviews/{reviewId}/questions (backend/lambdas/ask_question)."
}

variable "list_questions_zip_path" {
  type        = string
  description = "Deployment package for GET /reviews/{reviewId}/questions (backend/lambdas/list_questions)."
}

variable "review_questions_table_name" {
  type = string
}

variable "review_questions_table_arn" {
  type = string
}

variable "usage_counters_table_name" {
  type = string
}

variable "usage_counters_table_arn" {
  type = string
}

variable "chat_guardrail_id" {
  type = string
}

variable "chat_guardrail_version" {
  type = string
}

variable "chat_guardrail_arn" {
  type = string
}

variable "chat_grounding_guardrail_id" {
  type = string
}

variable "chat_grounding_guardrail_version" {
  type = string
}

variable "chat_grounding_guardrail_arn" {
  type = string
}

variable "chat_grounding_check_enabled" {
  type        = bool
  default     = true
  description = "Log contextual grounding scores for chat answers (detect-only, never blocks). About $0.0006 a question."
}

variable "vector_bucket_name" {
  type = string
}

variable "vector_index_name" {
  type = string
}

variable "chat_model_id" {
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
  description = "Model for chat answers; must be in chat_model_ids. Defaults to Sonnet 4.6 because Haiku 4.5's Marketplace subscription can't be completed for this account. The chat eval picks the cheapest model that passes (ADR-0050 §8)."
}

variable "chat_model_ids" {
  type        = list(string)
  default     = ["us.anthropic.claude-haiku-4-5-20251001-v1:0", "us.anthropic.claude-sonnet-4-6"]
  description = "Models the chat role may invoke, so switching chat_model_id needs no IAM change. Each must also be allowed by the runtime boundary (modules/iam)."
}

variable "chat_public_enabled" {
  type        = bool
  default     = false
  description = "The chat handlers refuse every caller unless true."
}

variable "chat_questions_per_review" {
  type    = number
  default = 5
}

variable "chat_blocked_per_review" {
  type    = number
  default = 5
}

variable "chat_daily_budget_micro_usd" {
  type        = number
  default     = 1000000
  description = "Estimated chat spend allowed per UTC day, in millionths of a dollar ($1.00, sized for Sonnet pricing). This is the hard stop; tune it from measured cost."
}

variable "chat_daily_max_questions" {
  type    = number
  default = 100
}

variable "chat_throttling_burst_limit" {
  type    = number
  default = 5
}

variable "chat_throttling_rate_limit" {
  type    = number
  default = 2
}

variable "chat_alarms_enabled" {
  type        = bool
  default     = false
  description = "Create the chat's metric filters and alarms. Needs the deploy-role statement in infra/environments/dev/proposed-chat-iam.md first."
}

variable "alarm_topic_arn" {
  type        = string
  default     = null
  description = "SNS topic for chat alarms (the budget alerts topic)."
}

variable "lambda_log_retention_days" {
  description = "Days to keep Lambda logs. Must be a value CloudWatch Logs accepts."
  type        = number
  default     = 30
}
