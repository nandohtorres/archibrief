# Terraform module: cost-controls
# ADR-0030/ADR-0040's remaining infra-layer pieces: a multi-tier AWS
# Budgets alert (target/alert threshold, not an enforced cap — AWS
# Budgets has no native action to halt Bedrock spend). The application
# kill switch ADR-0030 also calls for lives in the separate kill-switch
# module — see that module's header for why (avoids a module dependency
# cycle).
#
# No WAF Web ACL here, deliberately. Tried associating one with the API
# Gateway HTTP API (v2) stage and hit a real AWS constraint discovered
# at apply time: AWS WAF Web ACLs can only associate with API Gateway
# REST API (v1) stages, not HTTP APIs — also ALB, CloudFront, AppSync,
# Cognito user pools, App Runner, Verified Access. ArchiBrief's API is
# deliberately HTTP API (ADR-0016), so WAF-in-front-of-the-admin-endpoint
# isn't available without a bigger rearchitecture (REST API migration, or
# fronting the API with its own CloudFront distribution). ADR-0030's
# layered controls already list "API Gateway throttling" — already live
# on the stage (api-gateway module's throttling_burst_limit/
# throttling_rate_limit) — as the best-effort volumetric layer; this
# module doesn't duplicate it with something AWS won't let it attach.

resource "aws_sns_topic" "budget_alerts" {
  name = "${var.name_prefix}-budget-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "budget_alerts_email" {
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Multi-tier alerts per ADR-0040 ("set multiple alert tiers below and at
# the target") — 50/80/100% of the real measured spend, plus a forecasted
# tier so a runaway trend surfaces before the month ends, not after.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_sns_topic_arns  = [aws_sns_topic.budget_alerts.arn]
    }
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }
}
