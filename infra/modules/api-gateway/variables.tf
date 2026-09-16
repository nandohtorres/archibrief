variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "state_machine_arn" {
  type = string
}

variable "domain_name" {
  type    = string
  default = "api.archibrief.dev"
}

variable "throttling_burst_limit" {
  type    = number
  default = 20
}

variable "throttling_rate_limit" {
  type    = number
  default = 10
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "admin_authorizer_zip_path" {
  type        = string
  description = "Deployment package for the pre-shared admin-credential Lambda authorizer (ADR-0044)."
}

variable "permissions_boundary_arn" {
  type        = string
  description = "IAM permissions boundary applied to every role this module creates and passes to lambda.amazonaws.com/apigateway.amazonaws.com — see modules/iam's runtime_permissions_boundary_arn output and Work-Project-Issues-Log.md, 2026-09-09."
}
