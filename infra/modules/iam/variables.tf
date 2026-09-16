variable "name_prefix" {
  type    = string
  default = "archibrief"
}

# TODO(account-setup): the real value only exists once the AWS account's
# OIDC identity provider for GitHub Actions is registered during bootstrap.
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

variable "tags" {
  type    = map(string)
  default = {}
}
