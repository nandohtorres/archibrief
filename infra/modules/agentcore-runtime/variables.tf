variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "agent_runtime_zip_path" {
  type        = string
  description = "Path to the AgentCore Runtime deployment package (backend/agent/runtime_entrypoint.py + dependencies, built for Linux ARM64) — TODO(account-setup): does not exist until a real CI packaging step runs, same deferral as modules/step-functions-lambda's lambda_zip_paths."
}

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to the runtime execution role — see modules/iam's runtime_permissions_boundary_arn output."
}

variable "guardrail_id" {
  type        = string
  description = "Deployed Bedrock Guardrail ID (ADR-0033) — see modules/guardrails."
}

variable "guardrail_version" {
  type        = string
  description = "Deployed Bedrock Guardrail version — see modules/guardrails."
}

variable "vector_bucket_name" {
  type        = string
  description = "S3 Vectors bucket name (ADR-0007) — see modules/s3-vectors."
}

variable "vector_index_name" {
  type        = string
  description = "S3 Vectors index name, paired with vector_bucket_name."
}

# Same temporary Sonnet-4.6 placeholder as validate_reason_node.py and
# runtime_entrypoint.py's own env-var default — kept in sync deliberately.
# See Work-Project-Issues-Log.md/[[project_archibrief_rag_progress]] for
# the Sonnet 5 access-blocker history and revert instructions.
variable "reasoning_model_id" {
  type    = string
  default = "us.anthropic.claude-sonnet-4-6"
}

variable "reasoning_max_tokens" {
  type    = number
  default = 8192
}

variable "tags" {
  type    = map(string)
  default = {}
}
