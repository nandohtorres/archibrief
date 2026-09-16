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
  description = "Public domain, registered 2026-09-08 (Work-Project-Cost-Log.md)."
  default     = "archibrief.dev"
}

# TODO(account-setup): every variable below is a real placeholder until
# AWS account/IAM bootstrap (Work-Project-Deployment-Roadmap.md). See
# terraform.tfvars.example for the values to override per-environment.

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

variable "agentcore_runtime_arn" {
  type    = string
  default = null
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

variable "admin_authorizer_zip_path" {
  type        = string
  description = "Deployment package for the pre-shared admin-credential Lambda authorizer (ADR-0044)."
}

# Titan V2's actual output dimension — baseline candidate, not a final
# locked choice (ADR-0035). Confirm against the live retrieval evaluation
# before treating this as settled.
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
