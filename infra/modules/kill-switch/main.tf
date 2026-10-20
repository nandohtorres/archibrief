# Terraform module: kill-switch
# ADR-0030's "fast application kill switch checked before paid work
# starts". Its own module rather than part of cost-controls, so
# step-functions-lambda and api-gateway can depend on it without creating
# a module dependency cycle.
#
# ignore_changes on value: flipping this manually (console/CLI) during an
# incident must survive the next `terraform apply` instead of being reset
# to the default.

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
