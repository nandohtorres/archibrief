# Terraform module: step-functions-lambda
# Step Functions (Standard) owns only the durable outer job lifecycle —
# accept, validate, persist input, invoke the agent stage once,
# validate/persist result, publish status (ADR-0028). Each bounded
# stateless Lambda (Ingest, RuleEngine, Validate, Audit, Finalize) gets
# its own least-privilege execution role defined right here, in the same
# module as the Lambda itself (ADR-0021) — never a shared/generic role.
# The one reasoning/retrieval subworkflow runs in AgentCore Runtime, not
# duplicated here — the state machine below calls it once via an AWS SDK
# integration task, referencing an already-deployed AgentCore Runtime
# (agentcore_runtime_arn) that doesn't exist until account bootstrap.

locals {
  lambda_specs = {
    ingest      = { handler = "backend.lambdas.ingest.handler.handler", zip = var.lambda_zip_paths.ingest }
    rule_engine = { handler = "backend.lambdas.rule_engine.handler.handler", zip = var.lambda_zip_paths.rule_engine }
    validate    = { handler = "backend.lambdas.validate.handler.handler", zip = var.lambda_zip_paths.validate }
    audit       = { handler = "backend.lambdas.audit.handler.handler", zip = var.lambda_zip_paths.audit }
    finalize    = { handler = "backend.lambdas.finalize.handler.handler", zip = var.lambda_zip_paths.finalize }
  }
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

resource "aws_iam_role" "lambda" {
  for_each           = local.lambda_specs
  name               = "${var.name_prefix}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  for_each   = local.lambda_specs
  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Ingest/RuleEngine/Validate are pure compute on their event payload —
# no direct DynamoDB/S3 access needed beyond CloudWatch Logs.
data "aws_iam_policy_document" "audit_finalize_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem"]
    resources = [var.reviews_table_arn, var.audit_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "audit_finalize_data_access" {
  for_each = toset(["audit", "finalize"])
  name     = "${var.name_prefix}-${each.key}-data-access"
  role     = aws_iam_role.lambda[each.key].id
  policy   = data.aws_iam_policy_document.audit_finalize_data_access.json
}

resource "aws_lambda_function" "this" {
  for_each      = local.lambda_specs
  function_name = "${var.name_prefix}-${each.key}"
  role          = aws_iam_role.lambda[each.key].arn
  handler       = each.value.handler
  runtime       = "python3.12"
  filename      = each.value.zip
  source_code_hash = fileexists(each.value.zip) ? filebase64sha256(each.value.zip) : null

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/states/${var.name_prefix}-review"
  retention_in_days = 90
  tags              = var.tags
}

data "aws_iam_policy_document" "state_machine_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "state_machine" {
  name               = "${var.name_prefix}-review-state-machine"
  assume_role_policy = data.aws_iam_policy_document.state_machine_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "state_machine_invoke" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [for fn in aws_lambda_function.this : fn.arn]
  }

  dynamic "statement" {
    for_each = var.agentcore_runtime_arn == null ? [] : [1]
    content {
      effect    = "Allow"
      actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
      resources = [var.agentcore_runtime_arn]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "state_machine_invoke" {
  name   = "${var.name_prefix}-review-state-machine-invoke"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.state_machine_invoke.json
}

# Outer job lifecycle only (ADR-0028) — accept/validate/persist input,
# invoke Ingest -> RuleEngine -> the Agent subworkflow once -> Validate ->
# Audit -> Finalize, publish status. The PreflightGate pause/resume and
# Retrieve/Reason loop live inside AgentCore, not duplicated as states
# here — "InvokeAgent" is a single opaque task from this state machine's
# perspective.
resource "aws_sfn_state_machine" "review" {
  name     = "${var.name_prefix}-review"
  role_arn = aws_iam_role.state_machine.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "ArchiBrief review pipeline outer job lifecycle (ADR-0028)"
    StartAt = "Ingest"
    States = {
      Ingest = {
        Type     = "Task"
        Resource = aws_lambda_function.this["ingest"].arn
        Next     = "RuleEngine"
      }
      RuleEngine = {
        Type     = "Task"
        Resource = aws_lambda_function.this["rule_engine"].arn
        Next     = "InvokeAgent"
      }
      InvokeAgent = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
        Parameters = {
          "AgentRuntimeArn" = var.agentcore_runtime_arn
          "Payload.$"       = "$"
        }
        Next = "Validate"
      }
      Validate = {
        Type     = "Task"
        Resource = aws_lambda_function.this["validate"].arn
        Next     = "Audit"
      }
      Audit = {
        Type     = "Task"
        Resource = aws_lambda_function.this["audit"].arn
        Next     = "Finalize"
      }
      Finalize = {
        Type     = "Task"
        Resource = aws_lambda_function.this["finalize"].arn
        End      = true
      }
    }
  })

  tags = var.tags
}
