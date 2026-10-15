variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "lambda_zip_paths" {
  type = object({
    ingest                    = string
    rule_engine               = string
    validate                  = string
    audit                     = string
    finalize                  = string
    store_clarification_token = string
  })
  description = "Path to each Lambda's deployment package — TODO(account-setup): real build artifacts don't exist until a packaging step runs in CI."
}

variable "reports_bucket_arn" {
  type = string
}

variable "reports_bucket_name" {
  type        = string
  description = "S3 bucket name (not ARN) for Finalize's Parameters and the state machine's own literal reference — a Terraform-known infra constant, never caller-supplied input (see 2026-09-17 fix: this used to be sourced from the StartExecution request body, which leaked an internal resource name into the public API contract)."
}

variable "reviews_table_arn" {
  type = string
}

variable "reviews_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN) for Finalize's Parameters and the leading idempotency-check Task — same Terraform-known-constant reasoning as reports_bucket_name."
}

variable "audit_table_arn" {
  type = string
}

variable "agentcore_runtime_arn" {
  type        = string
  description = "ARN of the deployed AgentCore Runtime hosting the PreflightGate/Retrieve/Reason subworkflow — TODO(account-setup): does not exist until AgentCore is deployed."
  default     = null
}

variable "lambda_reserved_concurrency" {
  type = number
  # -1 = unreserved (no PutFunctionConcurrency call at all) — this
  # account's actual Lambda concurrency ceiling is below 15 (confirmed
  # 2026-09-10: even 5 reserved total, 1 per function, still violated
  # the mandatory 10-unreserved minimum), almost certainly the default
  # throttle on a brand-new AWS account. The admin-authorizer Lambda has
  # used -1 from the start and never hit this error. Revisit with an explicit cap
  # once the account's real limit is known (needs lambda:GetAccountSettings,
  # not currently granted) or after AWS raises it with usage history.
  default = -1
}

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to every role this module creates and passes to lambda.amazonaws.com/states.amazonaws.com — see modules/iam's runtime_permissions_boundary_arn output and Work-Project-Issues-Log.md, 2026-09-09."
}

variable "guardrail_id" {
  type        = string
  description = "Deployed Bedrock Guardrail ID (ADR-0033) — see modules/guardrails. Always supplied by the calling environment; a resource whose count depends on this being null can't be planned, since it's unknown until the guardrail is actually created."
}

variable "guardrail_version" {
  type        = string
  description = "Deployed Bedrock Guardrail version, paired with guardrail_id."
}

variable "kill_switch_parameter_name" {
  type        = string
  description = "SSM Parameter Store name (from modules/kill-switch) checked by the state machine's first state before any paid work starts (ADR-0030)."
}

variable "kill_switch_parameter_arn" {
  type        = string
  description = "SSM Parameter Store ARN, paired with kill_switch_parameter_name — used to scope the state machine role's ssm:GetParameter permission."
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "mark_review_failed_zip_path" {
  type        = string
  default     = "../../../backend/lambdas/mark_review_failed/build/mark_review_failed.zip"
  description = "Deployment package for the mark-review-failed Lambda (built by scripts/package_lambdas.py)."
}

variable "max_clarification_rounds" {
  type        = number
  default     = 2
  description = "How many times one review may pause for clarification before it fails with ClarificationLimitReached."
}
