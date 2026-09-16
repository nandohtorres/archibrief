variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "lambda_zip_paths" {
  type = object({
    ingest      = string
    rule_engine = string
    validate    = string
    audit       = string
    finalize    = string
  })
  description = "Path to each Lambda's deployment package — TODO(account-setup): real build artifacts don't exist until a packaging step runs in CI."
}

variable "reports_bucket_arn" {
  type = string
}

variable "reviews_table_arn" {
  type = string
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

variable "tags" {
  type    = map(string)
  default = {}
}
