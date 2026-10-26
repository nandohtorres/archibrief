variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "monthly_budget_usd" {
  type        = number
  default     = 50
  description = "Monthly AWS budget. Alerts at 50/80/100% actual and 100% forecast; at stop_threshold_percent actual the kill switch turns on."
}

variable "stop_threshold_percent" {
  type        = number
  default     = 90
  description = "Actual spend, as a percentage of monthly_budget_usd, at which the kill switch turns on."
}

variable "kill_switch_parameter_name" {
  type = string
}

variable "kill_switch_parameter_arn" {
  type = string
}

variable "permissions_boundary_arn" {
  type = string
}

variable "spend_stop_zip_path" {
  type    = string
  default = "../../../backend/lambdas/spend_stop/build/spend_stop.zip"
}

variable "alert_email" {
  type        = string
  description = "Email address for budget-threshold SNS notifications. Required — no default, so a real address must be supplied via terraform.tfvars (gitignored), never hardcoded here."
}

variable "tags" {
  type    = map(string)
  default = {}
}
