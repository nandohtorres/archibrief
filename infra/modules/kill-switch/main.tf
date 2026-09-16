# Terraform module: kill-switch
# ADR-0030's "fast application kill switch checked before paid work
# starts" — split into its own module (rather than living in
# cost-controls alongside WAF/Budgets) purely to avoid a module
# dependency cycle: step-functions-lambda needs this parameter, but
# api-gateway needs step-functions-lambda's state machine ARN, and
# cost-controls' WAF association needs api-gateway's stage ARN.
#
# ignore_changes on value: flipping this manually (console/CLI) during a
# real incident must survive the next `terraform apply` without being
# silently reset back to the default.

resource "aws_ssm_parameter" "kill_switch" {
  name        = "/${var.name_prefix}/kill-switch"
  description = "ADR-0030 application kill switch — set to \"true\" to make the review pipeline fail fast before any paid Bedrock/AgentCore work starts."
  type        = "String"
  value       = var.kill_switch_default
  tags        = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}
