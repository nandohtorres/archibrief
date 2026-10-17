# Content-bearing orchestration runs inside this Lambda, outside Standard
# execution history. Its input/output are identifiers and bounded status only.
variable "review_worker_zip_path" {
  type    = string
  default = "../../../backend/lambdas/review_worker/build/review_worker.zip"
}

resource "aws_iam_role" "review_worker" {
  name                 = "${var.name_prefix}-review-worker"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "review_worker_logs" {
  role       = aws_iam_role.review_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "review_worker" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [for name, fn in aws_lambda_function.this : fn.arn if name != "store_clarification_token"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/jobs/*"]
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
  dynamic "statement" {
    for_each = var.agentcore_runtime_arn == null ? [] : [1]
    content {
      actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
      resources = [var.agentcore_runtime_arn, "${var.agentcore_runtime_arn}/runtime-endpoint/*"]
    }
  }
}

resource "aws_iam_role_policy" "review_worker" {
  role   = aws_iam_role.review_worker.id
  policy = data.aws_iam_policy_document.review_worker.json
}

resource "aws_lambda_function" "review_worker" {
  function_name    = "${var.name_prefix}-review-worker"
  role             = aws_iam_role.review_worker.arn
  handler          = "backend.lambdas.review_worker.handler.handler"
  runtime          = "python3.12"
  filename         = var.review_worker_zip_path
  source_code_hash = fileexists(var.review_worker_zip_path) ? filebase64sha256(var.review_worker_zip_path) : null
  timeout          = 900
  memory_size      = 512

  environment {
    variables = merge({
      REVIEWS_TABLE_NAME         = var.reviews_table_name
      REPORTS_BUCKET_NAME        = var.reports_bucket_name
      KILL_SWITCH_PARAMETER_NAME = var.kill_switch_parameter_name
      MAX_CLARIFICATION_ROUNDS   = tostring(var.max_clarification_rounds)
      AGENTCORE_RUNTIME_ARN      = coalesce(var.agentcore_runtime_arn, "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/not-yet-deployed")
    }, { for name, fn in aws_lambda_function.this : "${upper(name)}_FUNCTION_NAME" => fn.function_name })
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "review_worker" {
  name              = "/aws/lambda/${aws_lambda_function.review_worker.function_name}"
  retention_in_days = 7
  tags              = var.tags
}
