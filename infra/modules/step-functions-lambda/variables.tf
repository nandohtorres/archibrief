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
  type    = number
  default = 5
}

variable "tags" {
  type    = map(string)
  default = {}
}
