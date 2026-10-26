# The hard stop behind the monthly budget. AWS Budgets can't halt Bedrock
# spend itself, so its stop notification goes to a dedicated topic whose
# only subscriber turns the application kill switch on. Billing data lags
# by hours, so this is the backstop; the app's monthly admission ceiling
# (paid_limits.global_monthly_budget) is the real-time limit.

data "aws_caller_identity" "current" {}

locals {
  alert_topics = {
    alerts = aws_sns_topic.budget_alerts.arn
    stop   = aws_sns_topic.spend_stop.arn
  }
}

# AWS Budgets and CloudWatch alarms publish as services, which the default
# topic policy doesn't admit.
data "aws_iam_policy_document" "service_publish" {
  for_each = local.alert_topics

  statement {
    sid    = "AccountOwnerManages"
    effect = "Allow"
    actions = [
      "SNS:GetTopicAttributes",
      "SNS:SetTopicAttributes",
      "SNS:Subscribe",
      "SNS:ListSubscriptionsByTopic",
      "SNS:Publish",
    ]
    resources = [each.value]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid       = "ServicesPublish"
    effect    = "Allow"
    actions   = ["SNS:Publish"]
    resources = [each.value]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com", "cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "service_publish" {
  for_each = local.alert_topics
  arn      = each.value
  policy   = data.aws_iam_policy_document.service_publish[each.key].json
}

resource "aws_sns_topic" "spend_stop" {
  name = "${var.name_prefix}-spend-stop"
  tags = var.tags
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "spend_stop" {
  name                 = "${var.name_prefix}-spend-stop"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "spend_stop_logs" {
  role       = aws_iam_role.spend_stop.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Write access to the kill-switch parameter, and nothing else.
data "aws_iam_policy_document" "spend_stop" {
  statement {
    effect    = "Allow"
    actions   = ["ssm:PutParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
}

resource "aws_iam_role_policy" "spend_stop" {
  name   = "${var.name_prefix}-spend-stop"
  role   = aws_iam_role.spend_stop.id
  policy = data.aws_iam_policy_document.spend_stop.json
}

resource "aws_cloudwatch_log_group" "spend_stop" {
  name              = "/aws/lambda/${var.name_prefix}-spend-stop"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_lambda_function" "spend_stop" {
  function_name    = "${var.name_prefix}-spend-stop"
  role             = aws_iam_role.spend_stop.arn
  handler          = "backend.lambdas.spend_stop.handler.handler"
  runtime          = "python3.12"
  filename         = var.spend_stop_zip_path
  source_code_hash = fileexists(var.spend_stop_zip_path) ? filebase64sha256(var.spend_stop_zip_path) : null
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      KILL_SWITCH_PARAMETER_NAME = var.kill_switch_parameter_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.spend_stop]
  tags       = var.tags
}

resource "aws_lambda_permission" "spend_stop_sns" {
  statement_id  = "AllowSpendStopTopic"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.spend_stop.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.spend_stop.arn
}

resource "aws_sns_topic_subscription" "spend_stop" {
  topic_arn = aws_sns_topic.spend_stop.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.spend_stop.arn
}
