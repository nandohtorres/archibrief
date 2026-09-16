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

variable "vector_bucket_name" {
  type        = string
  description = "S3 Vectors bucket name (ADR-0007) — see modules/s3-vectors."
}

variable "vector_index_name" {
  type        = string
  description = "S3 Vectors index name, paired with vector_bucket_name."
}

variable "tags" {
  type    = map(string)
  default = {}
}
