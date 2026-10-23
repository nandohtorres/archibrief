# Terraform module: cost-controls
# ADR-0030/ADR-0040's infra-layer cost controls: a multi-tier AWS Budgets
# alert (a target/alert threshold, not an enforced cap; AWS Budgets has no
# native action to halt Bedrock spend). The application kill switch
# ADR-0030 also calls for lives in the separate kill-switch module to
# avoid a module dependency cycle.
#
# WAF can't attach to an HTTP API (v2), so the public front door is a
# separate REST API stage with its own Web ACL (api-gateway module,
# public-edge.tf). Stage throttling is the volumetric layer on both.

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
# the target"): 50/80/100% of actual spend, plus a forecasted
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
      comparison_operator       = "GREATER_THAN"
      threshold                 = notification.value
      threshold_type            = "PERCENTAGE"
      notification_type         = "ACTUAL"
      subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
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
