variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "monthly_budget_usd" {
  type        = number
  default     = 50
  description = "ADR-0024/ADR-0040 — target/alert threshold, not an enforced ceiling. AWS Budgets has no native action to halt Bedrock spend."
}

variable "alert_email" {
  type        = string
  description = "Email address for budget-threshold SNS notifications. Required — no default, so a real address must be supplied via terraform.tfvars (gitignored), never hardcoded here."
}

variable "tags" {
  type    = map(string)
  default = {}
}
