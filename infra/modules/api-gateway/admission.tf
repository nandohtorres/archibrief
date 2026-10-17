variable "submit_review_zip_path" {
  type    = string
  default = "../../../backend/lambdas/submit_review/build/submit_review.zip"
}

variable "turnstile_secret_parameter_arn" {
  type    = string
  default = null
}

variable "turnstile_secret_parameter_name" {
  type    = string
  default = ""
}

variable "turnstile_hostname" {
  type    = string
  default = ""
}

variable "public_access_enabled" {
  type    = bool
  default = false
  validation {
    condition = !var.public_access_enabled || (var.public_edge_enabled && var.verified_public_api_id != "" && var.turnstile_secret_parameter_arn != null && var.turnstile_secret_parameter_name != "" && var.turnstile_hostname != "")
    error_message = "Public access requires the WAF REST front door and configured Turnstile verification."
  }
}

variable "verified_public_api_id" {
  type        = string
  default     = ""
  description = "REST API ID copied only after an admin-only deployment and WAF bypass checks."
}

resource "random_password" "visitor_hash" {
  length  = 48
  special = false
}

resource "random_password" "reservation" {
  length  = 48
  special = false
}

locals {
  public_admitted = var.public_edge_enabled ? (var.public_access_enabled && var.verified_public_api_id == aws_api_gateway_rest_api.public[0].id) : false
  admission_environment = {
    ADMIN_KEY                       = random_password.admin_key.result
    PUBLIC_ACCESS_ENABLED           = local.public_admitted ? "true" : "false"
    VISITOR_HASH_KEY                 = random_password.visitor_hash.result
    TURNSTILE_SECRET_PARAMETER_NAME  = var.turnstile_secret_parameter_name
    TURNSTILE_HOSTNAME               = var.turnstile_hostname
    USAGE_COUNTERS_TABLE_NAME        = var.usage_counters_table_name
    REVIEWS_TABLE_NAME               = var.reviews_table_name
    REPORTS_BUCKET_NAME              = var.reports_bucket_name
    KILL_SWITCH_PARAMETER_NAME       = var.kill_switch_parameter_name
    CORS_ALLOWED_ORIGINS             = jsonencode(concat([var.frontend_origin], var.additional_cors_origins))
  }
}

resource "aws_iam_role" "submit_review" {
  name                 = "${var.name_prefix}-submit-review"
  assume_role_policy   = data.aws_iam_policy_document.admin_authorizer_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "submit_review_logs" {
  role       = aws_iam_role.submit_review.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "submit_review" {
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    actions   = ["s3:GetObjectVersion"]
    resources = ["${var.reports_bucket_arn}/uploads/*"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/jobs/*"]
  }
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
  statement {
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }
}

resource "aws_iam_role_policy" "submit_review" {
  role   = aws_iam_role.submit_review.id
  policy = data.aws_iam_policy_document.submit_review.json
}

resource "aws_lambda_function" "submit_review" {
  function_name    = "${var.name_prefix}-submit-review"
  role             = aws_iam_role.submit_review.arn
  handler          = "backend.lambdas.submit_review.handler.handler"
  runtime          = "python3.12"
  filename         = var.submit_review_zip_path
  source_code_hash = fileexists(var.submit_review_zip_path) ? filebase64sha256(var.submit_review_zip_path) : null
  timeout          = 28
  memory_size      = 256
  environment {
    variables = merge(local.admission_environment, { STATE_MACHINE_ARN = var.state_machine_arn })
  }
  tags = var.tags
}

resource "aws_lambda_permission" "submit_review_http_api" {
  statement_id  = "AllowHTTPAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit_review.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_iam_role_policy" "shared_paid_counters" {
  for_each = {
    upload  = aws_iam_role.create_upload.name
    submit  = aws_iam_role.submit_review.name
    deeper  = aws_iam_role.deeper_review.name
    clarify = aws_iam_role.clarify_review.name
  }
  role = each.value
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
      Resource = var.usage_counters_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "upload_reservations" {
  role = aws_iam_role.create_upload.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
      Resource = var.reviews_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "turnstile_secret" {
  count = var.turnstile_secret_parameter_arn == null ? 0 : 1
  role  = aws_iam_role.create_upload.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = var.turnstile_secret_parameter_arn
    }]
  })
}

resource "aws_iam_role_policy" "clarification_objects" {
  role = aws_iam_role.clarify_review.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${var.reports_bucket_arn}/jobs/*"
    }]
  })
}
