# Report chat (ADR-0046 §4, ADR-0050): POST and GET
# /reviews/{reviewId}/questions.
#
# Admin-gated like every other non-demo route until Phase 3 builds the
# visitor limits; the handlers also refuse non-admin callers unless
# chat_public_enabled is true, so removing the authorizer alone can't
# open a paid public endpoint.
#
# ask_question makes the one paid call (Bedrock Converse), so its role can
# invoke only the chat models, the embedding model, the two chat
# guardrails and the corpus index, and read only reports/ and parsed/.
# No reserved concurrency: this account's Lambda limit is below the
# 10-unreserved minimum (see step-functions-lambda's
# lambda_reserved_concurrency); route throttling and the daily $ cap
# bound cost instead.

data "aws_caller_identity" "current" {}

locals {
  # A cross-region profile ("us.anthropic...") needs the profile ARN and
  # the foundation model in every region it routes to.
  chat_model_resources = flatten([
    for id in var.chat_model_ids : [
      "arn:aws:bedrock:*::foundation-model/${trimprefix(id, "us.")}",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/${id}",
    ]
  ])
}

# A marker in the system prompt that must never appear in an answer
# (ADR-0050 §4). Per deploy, never committed, only in the Lambda's env.
resource "random_password" "chat_canary" {
  length  = 24
  special = false
}

data "aws_iam_policy_document" "ask_question_access" {
  statement {
    # ADR-0030 kill switch, checked first; fails closed.
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
  statement {
    # The review's question counter and blocked counter.
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    # Question records, stored suggested answers, history.
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [var.review_questions_table_arn]
  }
  statement {
    # The day's chat budget and question count.
    effect    = "Allow"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.usage_counters_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/reports/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:GetInferenceProfile"]
    resources = local.chat_model_resources
  }
  statement {
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"]
  }
  statement {
    effect    = "Allow"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [var.chat_guardrail_arn, var.chat_grounding_guardrail_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3vectors:QueryVectors", "s3vectors:GetVectors"]
    resources = ["arn:aws:s3vectors:*:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket_name}/index/${var.vector_index_name}"]
  }
}

data "aws_iam_policy_document" "list_questions_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:Query"]
    resources = [var.review_questions_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/reports/*"]
  }
}

locals {
  chat_functions = {
    ask_question = {
      name        = "${var.name_prefix}-ask-question"
      handler     = "backend.lambdas.ask_question.handler.handler"
      zip         = var.ask_question_zip_path
      policy      = data.aws_iam_policy_document.ask_question_access.json
      timeout     = 28 # under the 29 s integration; the model read timeout is 20 s
      memory_size = 512
    }
    list_questions = {
      name        = "${var.name_prefix}-list-questions"
      handler     = "backend.lambdas.list_questions.handler.handler"
      zip         = var.list_questions_zip_path
      policy      = data.aws_iam_policy_document.list_questions_access.json
      timeout     = 10
      memory_size = 256
    }
  }

  chat_common_environment = {
    REVIEWS_TABLE_NAME        = var.reviews_table_name
    QUESTIONS_TABLE_NAME      = var.review_questions_table_name
    REPORTS_BUCKET_NAME       = var.reports_bucket_name
    ADMIN_KEY                 = random_password.admin_key.result
    CHAT_PUBLIC_ENABLED       = var.chat_public_enabled ? "true" : "false"
    CHAT_QUESTIONS_PER_REVIEW = tostring(var.chat_questions_per_review)
  }

  chat_environment = {
    ask_question = merge(local.chat_common_environment, {
      USAGE_COUNTERS_TABLE_NAME        = var.usage_counters_table_name
      KILL_SWITCH_PARAMETER_NAME       = var.kill_switch_parameter_name
      CHAT_MODEL_ID                    = var.chat_model_id
      CHAT_GUARDRAIL_ID                = var.chat_guardrail_id
      CHAT_GUARDRAIL_VERSION           = var.chat_guardrail_version
      CHAT_GROUNDING_GUARDRAIL_ID      = var.chat_grounding_check_enabled ? var.chat_grounding_guardrail_id : ""
      CHAT_GROUNDING_GUARDRAIL_VERSION = var.chat_grounding_guardrail_version
      VECTOR_BUCKET_NAME               = var.vector_bucket_name
      VECTOR_INDEX_NAME                = var.vector_index_name
      CHAT_CANARY                      = random_password.chat_canary.result
      CHAT_DAILY_BUDGET_MICRO_USD      = tostring(var.chat_daily_budget_micro_usd)
      CHAT_DAILY_MAX_QUESTIONS         = tostring(var.chat_daily_max_questions)
      CHAT_BLOCKED_PER_REVIEW          = tostring(var.chat_blocked_per_review)
    })
    list_questions = local.chat_common_environment
  }
}

resource "aws_iam_role" "chat" {
  for_each             = local.chat_functions
  name                 = each.value.name
  assume_role_policy   = data.aws_iam_policy_document.admin_authorizer_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "chat_basic_logs" {
  for_each   = local.chat_functions
  role       = aws_iam_role.chat[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "chat_access" {
  for_each = local.chat_functions
  name     = "${each.value.name}-access"
  role     = aws_iam_role.chat[each.key].id
  policy   = each.value.policy
}

# Created before the functions so the 7-day retention applies from the
# first invocation (ADR-0050 §9; the chat logs carry no question text).
resource "aws_cloudwatch_log_group" "chat" {
  for_each          = local.chat_functions
  name              = "/aws/lambda/${each.value.name}"
  retention_in_days = 7
  tags              = var.tags
}

resource "aws_lambda_function" "chat" {
  for_each         = local.chat_functions
  function_name    = each.value.name
  role             = aws_iam_role.chat[each.key].arn
  handler          = each.value.handler
  runtime          = "python3.12"
  filename         = each.value.zip
  source_code_hash = fileexists(each.value.zip) ? filebase64sha256(each.value.zip) : null
  timeout          = each.value.timeout
  memory_size      = each.value.memory_size

  environment {
    variables = local.chat_environment[each.key]
  }

  depends_on = [aws_cloudwatch_log_group.chat]
  tags       = var.tags
}

resource "aws_lambda_permission" "apigw_invoke_chat" {
  for_each      = local.chat_functions
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chat[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "chat" {
  for_each               = local.chat_functions
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.chat[each.key].invoke_arn
  payload_format_version = "2.0"
  # Above the Lambda's own timeout, so its timeout response reaches the
  # caller rather than a bare gateway 503 (same as deeper_review, Codex F19).
  timeout_milliseconds = 29000
}

resource "aws_apigatewayv2_route" "post_questions" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /reviews/{reviewId}/questions"
  target             = "integrations/${aws_apigatewayv2_integration.chat["ask_question"].id}"
  authorizer_id      = aws_apigatewayv2_authorizer.admin_gate.id
  authorization_type = "CUSTOM"
}

resource "aws_apigatewayv2_route" "get_questions" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /reviews/{reviewId}/questions"
  target             = "integrations/${aws_apigatewayv2_integration.chat["list_questions"].id}"
  authorizer_id      = aws_apigatewayv2_authorizer.admin_gate.id
  authorization_type = "CUSTOM"
}

# --- Alarms (ADR-0050 §9), off until the deploy role can create them ---
# The deploy role has no logs:PutMetricFilter or cloudwatch:PutMetricAlarm
# yet; infra/environments/dev/proposed-chat-iam.md has the statement to
# add. Then set chat_alarms_enabled = true.

locals {
  chat_alarm_count = var.chat_alarms_enabled ? 1 : 0
  chat_metrics = {
    canary_hits = {
      pattern = "{ $.canary_hit IS TRUE }"
      value   = "1"
    }
    blocked = {
      pattern = "{ $.outcome = \"blocked\" }"
      value   = "1"
    }
    failed = {
      pattern = "{ $.outcome = \"failed\" }"
      value   = "1"
    }
    cost_micro_usd = {
      pattern = "{ $.est_cost_micro_usd > 0 }"
      value   = "$.est_cost_micro_usd"
    }
  }
}

resource "aws_cloudwatch_log_metric_filter" "chat" {
  for_each       = var.chat_alarms_enabled ? local.chat_metrics : {}
  name           = "${var.name_prefix}-chat-${each.key}"
  log_group_name = aws_cloudwatch_log_group.chat["ask_question"].name
  pattern        = each.value.pattern

  metric_transformation {
    name          = "chat_${each.key}"
    namespace     = "ArchiBrief/Chat"
    value         = each.value.value
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "chat_canary" {
  count               = local.chat_alarm_count
  alarm_name          = "${var.name_prefix}-chat-canary-leak"
  alarm_description   = "The chat's system-prompt canary appeared in an answer (it was replaced by a refusal). Look for a prompt-extraction attempt."
  namespace           = "ArchiBrief/Chat"
  metric_name         = "chat_canary_hits"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.chat]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "chat_blocked" {
  count               = local.chat_alarm_count
  alarm_name          = "${var.name_prefix}-chat-blocked-spike"
  alarm_description   = "More than 20 chat questions blocked by Guardrails in an hour."
  namespace           = "ArchiBrief/Chat"
  metric_name         = "chat_blocked"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.chat]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "chat_failed" {
  count               = local.chat_alarm_count
  alarm_name          = "${var.name_prefix}-chat-failures"
  alarm_description   = "More than 5 chat answers failed (timeout or malformed output) in 15 minutes."
  namespace           = "ArchiBrief/Chat"
  metric_name         = "chat_failed"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.chat]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "chat_cost" {
  count               = local.chat_alarm_count
  alarm_name          = "${var.name_prefix}-chat-daily-cost"
  alarm_description   = "Estimated chat spend reached 80% of the daily chat budget."
  namespace           = "ArchiBrief/Chat"
  metric_name         = "chat_cost_micro_usd"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = floor(var.chat_daily_budget_micro_usd * 0.8)
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.chat]
  tags                = var.tags
}
