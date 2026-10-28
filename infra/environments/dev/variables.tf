variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "domain" {
  type        = string
  description = "Public domain for the site and API."
  default     = "archibrief.dev"
}

# Account-specific values; see terraform.tfvars.example for what to set
# per environment.

variable "aws_account_id" {
  type = string
}

variable "github_oidc_provider_arn" {
  type    = string
  default = null
}

variable "github_repo" {
  type    = string
  default = "REPLACE_ME/archibrief"
}

variable "github_oidc_subject_prefix" {
  type        = string
  default     = null
  description = "GitHub OIDC sub_claim_prefix from the repository API; set in ignored tfvars for immutable-subject repositories."
}

variable "lambda_zip_paths" {
  type = object({
    ingest      = string
    rule_engine = string
    validate    = string
    audit       = string
    finalize    = string
  })
}

variable "get_review_zip_path" {
  type        = string
  description = "Deployment package for GET /reviews/{reviewId}'s Lambda (backend/lambdas/get_review)."
}

variable "deeper_review_zip_path" {
  type        = string
  description = "Deployment package for POST /reviews/{reviewId}/findings/{findingId}/deeper's Lambda (backend/lambdas/deeper_review)."
}

variable "get_demo_zip_path" {
  type        = string
  description = "Deployment package for GET /demo's Lambda (backend/lambdas/get_demo)."
}

variable "create_upload_zip_path" {
  type        = string
  description = "Deployment package for POST /uploads's Lambda (backend/lambdas/create_upload), ADR-0045."
}

variable "agentcore_runtime_zip_path" {
  type        = string
  description = "Deployment package for the AgentCore Runtime entrypoint (backend/agent/runtime_entrypoint.py); see modules/agentcore-runtime's agent_runtime_zip_path for packaging requirements."
}

variable "alert_email" {
  type        = string
  description = "Email address for AWS Budgets threshold notifications (ADR-0040). The real value goes in terraform.tfvars (gitignored), never here."
}

variable "monthly_budget_usd" {
  type        = number
  default     = 100
  description = "Monthly AWS budget: alert tiers, and at 90% actual spend the kill switch turns on (cost-controls module)."
}

# Titan V2's output dimension (ADR-0035). Immutable once the index
# exists.
variable "embedding_dimension" {
  type    = number
  default = 1024
}

variable "embedding_distance_metric" {
  type    = string
  default = "cosine"
}

variable "tags" {
  type = map(string)
  default = {
    Project = "archibrief"
  }
}

# Report chat (ADR-0050). Defaults point at scripts/package_lambdas.py's
# output, so terraform.tfvars needs no new lines.
variable "ask_question_zip_path" {
  type        = string
  default     = "../../../backend/lambdas/ask_question/build/ask_question.zip"
  description = "Deployment package for POST /reviews/{reviewId}/questions (backend/lambdas/ask_question)."
}

variable "list_questions_zip_path" {
  type        = string
  default     = "../../../backend/lambdas/list_questions/build/list_questions.zip"
  description = "Deployment package for GET /reviews/{reviewId}/questions (backend/lambdas/list_questions)."
}

variable "chat_alarms_enabled" {
  type        = bool
  default     = false
  description = "Chat metric filters and alarms. Needs the deploy-role statement in proposed-chat-iam.md first."
}

variable "create_github_oidc_provider" {
  type        = bool
  default     = false
  description = "Opt in to managing GitHub's account-wide OIDC provider. Leave false when reusing an existing provider ARN."
}
