# Same identifier-only Standard execution pattern as the initial review.
# Never retry a model-bearing task automatically, including on redrive:
# the worker's conditional pending -> running claim permits one attempt.
resource "aws_iam_role" "deeper_worker" {
  name                 = "${var.name_prefix}-deeper-worker"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "deeper_worker_logs" {
  role       = aws_iam_role.deeper_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "deeper_worker" {
  statement {
    actions   = ["dynamodb:GetItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [var.findings_table_arn]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/reports/*"]
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

resource "aws_iam_role_policy" "deeper_worker" {
  role   = aws_iam_role.deeper_worker.id
  policy = data.aws_iam_policy_document.deeper_worker.json
}

resource "aws_lambda_function" "deeper_worker" {
  function_name    = "${var.name_prefix}-deeper-worker"
  role             = aws_iam_role.deeper_worker.arn
  handler          = "backend.lambdas.deeper_review.worker.run_job"
  runtime          = "python3.12"
  filename         = var.deeper_review_zip_path
  source_code_hash = fileexists(var.deeper_review_zip_path) ? filebase64sha256(var.deeper_review_zip_path) : null
  timeout          = 350
  memory_size      = 512
  environment {
    variables = {
      REVIEWS_TABLE_NAME         = var.reviews_table_name
      FINDINGS_TABLE_NAME        = var.findings_table_name
      REPORTS_BUCKET_NAME        = var.reports_bucket_name
      KILL_SWITCH_PARAMETER_NAME = var.kill_switch_parameter_name
      AGENTCORE_RUNTIME_ARN      = coalesce(var.agentcore_runtime_arn, "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/not-yet-deployed")
    }
  }
  tags = var.tags
}

data "aws_iam_policy_document" "deeper_workflow_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "deeper_workflow" {
  name                 = "${var.name_prefix}-deeper-workflow"
  assume_role_policy   = data.aws_iam_policy_document.deeper_workflow_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy" "deeper_workflow" {
  role   = aws_iam_role.deeper_workflow.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [aws_lambda_function.deeper_worker.arn] }] })
}

resource "aws_cloudwatch_log_group" "deeper_workflow" {
  name              = "/aws/vendedlogs/states/${var.name_prefix}-deeper-review"
  retention_in_days = 7
  tags              = var.tags
}

resource "aws_iam_role_policy" "deeper_workflow_logs" {
  role = aws_iam_role.deeper_workflow.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow"
    Action   = ["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"]
    Resource = "*"
  }] })
}

resource "aws_sfn_state_machine" "deeper" {
  name     = "${var.name_prefix}-deeper-review"
  role_arn = aws_iam_role.deeper_workflow.arn
  type     = "STANDARD"
  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.deeper_workflow.arn}:*"
    include_execution_data = false
    level                  = "ALL"
  }
  definition = jsonencode({
    Comment        = "Identifier-only deeper job. Model calls are never retried."
    StartAt        = "Run"
    TimeoutSeconds = 400
    States = {
      Run = {
        Type       = "Task", Resource = aws_lambda_function.deeper_worker.arn, TimeoutSeconds = 360
        Parameters = { "review_id.$" = "$.review_id", "finding_id.$" = "$.finding_id", "job_id.$" = "$.job_id", phase = "run" }
        ResultPath = null
        Catch      = [{ ErrorEquals = ["States.ALL"], ResultPath = null, Next = "MarkFailed" }]
        End        = true
      }
      MarkFailed = {
        Type       = "Task", Resource = aws_lambda_function.deeper_worker.arn, TimeoutSeconds = 10
        Parameters = { "review_id.$" = "$.review_id", "finding_id.$" = "$.finding_id", "job_id.$" = "$.job_id", phase = "fail" }
        ResultPath = null, End = true
      }
    }
  })
  tags = var.tags
}
