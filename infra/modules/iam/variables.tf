variable "name_prefix" {
  type    = string
  default = "archibrief"
}

# Exists only once the account's OIDC identity provider for GitHub
# Actions is registered; the deploy role isn't created until then.
variable "github_oidc_provider_arn" {
  type        = string
  description = "ARN of the GitHub Actions OIDC provider, for the CI/CD deploy role's trust policy."
  default     = null
}

variable "github_repo" {
  type        = string
  description = "owner/repo allowed to assume the deploy role via OIDC."
  default     = "REPLACE_ME/archibrief"
}

variable "github_oidc_subject_prefix" {
  type        = string
  default     = null
  description = "Verified GitHub sub_claim_prefix (including immutable IDs when enabled). Null uses the legacy repo:owner/repo prefix."

  validation {
    condition     = var.github_oidc_subject_prefix == null ? true : replace(var.github_oidc_subject_prefix, "/@[0-9]+/", "") == "repo:${var.github_repo}"
    error_message = "The OIDC prefix must identify github_repo, optionally with GitHub's immutable owner and repository IDs."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "create_github_oidc_provider" {
  type        = bool
  default     = false
  description = "Opt in to managing GitHub's account-wide OIDC provider. Leave false when reusing an existing provider ARN."
}

variable "frontend_bucket_arn" {
  type        = string
  description = "Only bucket the GitHub frontend deploy role may publish."
}

variable "frontend_distribution_arn" {
  type        = string
  description = "Only CloudFront distribution the GitHub deploy role may invalidate."
}
