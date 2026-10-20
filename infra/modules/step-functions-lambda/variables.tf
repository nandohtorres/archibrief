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
  description = "Path to each Lambda's deployment package (built by scripts/package_lambdas.py)."
}

variable "reports_bucket_arn" {
  type = string
}

variable "reports_bucket_name" {
  type        = string
  description = "S3 bucket name (not ARN) injected as a literal into the state machine's task Parameters. A Terraform-known constant, never caller-supplied, so internal resource names stay out of the public API contract."
}

variable "reviews_table_arn" {
  type = string
}

variable "reviews_table_name" {
  type        = string
  description = "DynamoDB table name (not ARN) for Finalize's Parameters and the leading idempotency-check Task; a Terraform-known constant like reports_bucket_name."
}

variable "audit_table_arn" {
  type = string
}

variable "agentcore_runtime_arn" {
  type        = string
  description = "ARN of the deployed AgentCore Runtime hosting the PreflightGate/Retrieve/Reason subworkflow. While null, InvokeAgent uses a placeholder ARN and fails at execution time."
  default     = null
}

variable "lambda_reserved_concurrency" {
  type = number
  # -1 = unreserved (no PutFunctionConcurrency call). New AWS accounts can
  # have a Lambda concurrency limit so low that reserving even one unit per
  # function violates the mandatory 10-unreserved minimum. Set an explicit
  # cap once the account's limit allows it.
  default = -1
}

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to every role this module creates and passes to lambda.amazonaws.com/states.amazonaws.com (modules/iam's runtime_permissions_boundary_arn output)."
}

variable "guardrail_id" {
  type        = string
  description = "Deployed Bedrock Guardrail ID (ADR-0033) from modules/guardrails. Always required: a resource count conditioned on it can't be planned, since it is unknown until the guardrail is created."
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

# ADR-0048: Trivy scan step. Defaults point at the build outputs, so the
# environment's terraform.tfvars doesn't need new entries.
variable "scan_zip_path" {
  type        = string
  default     = "../../../backend/lambdas/scan/build/scan.zip"
  description = "Scan Lambda package (python scripts/package_lambdas.py scan)."
}

variable "trivy_layer_zip_path" {
  type        = string
  default     = "../../../backend/build/trivy-layer.zip"
  description = "Trivy layer zip (python scripts/build_trivy_layer.py)."
}

variable "trivy_version" {
  type        = string
  default     = "0.76.0"
  description = "Must match TRIVY_VERSION in scripts/build_trivy_layer.py."
}

variable "lambda_log_retention_days" {
  description = "Days to keep Lambda logs. Must be a value CloudWatch Logs accepts."
  type        = number
  default     = 30
}
