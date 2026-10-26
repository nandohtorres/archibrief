# Terraform module: api-gateway
# The API's Lambdas and the api.archibrief.dev domain. The routes, WAF and
# throttling live on the REST API in public-edge.tf. There are no user
# accounts; each handler enforces public access, capabilities and the
# spending limits itself (admission.tf). Throttling and WAF are best-effort
# layers, not a guaranteed ceiling (ADR-0005, ADR-0030).

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

# GET /reviews/{reviewId} and POST /reviews/{reviewId}/clarify need a
# DynamoDB read and a task-token resume (states:SendTaskSuccess), so both
# are Lambda proxy integrations.
data "aws_iam_policy_document" "review_reader_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:Query"]
    resources = [var.findings_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [var.reviews_table_arn]
  }
  # get_review reads the S3 evidence ledger to assemble the ReviewReport
  # (backend.shared.report) once a review is complete.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/*"]
  }
}

resource "aws_iam_role" "get_review" {
  name                 = "${var.name_prefix}-get-review"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "get_review_basic_logs" {
  role       = aws_iam_role.get_review.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "get_review_data_access" {
  name   = "${var.name_prefix}-get-review-data-access"
  role   = aws_iam_role.get_review.id
  policy = data.aws_iam_policy_document.review_reader_data_access.json
}

resource "aws_lambda_function" "get_review" {
  function_name    = "${var.name_prefix}-get-review"
  role             = aws_iam_role.get_review.arn
  handler          = "backend.lambdas.get_review.handler.handler"
  runtime          = "python3.12"
  filename         = var.get_review_zip_path
  source_code_hash = fileexists(var.get_review_zip_path) ? filebase64sha256(var.get_review_zip_path) : null
  # A finished report is read from S3, merged with deeper findings from
  # DynamoDB and projected; at 128 MB and 3 s that timed out every time.
  # Lambda CPU scales with memory.
  timeout     = 10
  memory_size = 512

  environment {
    variables = merge(local.admission_environment, {
      REVIEWS_TABLE_NAME  = var.reviews_table_name
      REPORTS_BUCKET_NAME = var.reports_bucket_name
      FINDINGS_TABLE_NAME = var.findings_table_name
    })
  }

  tags = var.tags
}

# clarify_review needs GetItem+UpdateItem (reads the pending token, then
# claims it with a conditional field-level update before resuming) plus
# states:SendTaskSuccess, which must be scoped to resource "*": the
# task-token API has no ARN-scoped resource, and the token itself is the
# authorization.
data "aws_iam_policy_document" "clarify_review_data_access" {
  statement {
    # ADR-0030 kill switch, checked before any paid work.
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "clarify_review" {
  name                 = "${var.name_prefix}-clarify-review"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "clarify_review_basic_logs" {
  role       = aws_iam_role.clarify_review.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "clarify_review_data_access" {
  name   = "${var.name_prefix}-clarify-review-data-access"
  role   = aws_iam_role.clarify_review.id
  policy = data.aws_iam_policy_document.clarify_review_data_access.json
}

resource "aws_lambda_function" "clarify_review" {
  function_name    = "${var.name_prefix}-clarify-review"
  role             = aws_iam_role.clarify_review.arn
  handler          = "backend.lambdas.clarify_review.handler.handler"
  runtime          = "python3.12"
  filename         = var.clarify_review_zip_path
  source_code_hash = fileexists(var.clarify_review_zip_path) ? filebase64sha256(var.clarify_review_zip_path) : null
  timeout          = 10

  environment {
    variables = merge(local.admission_environment, {
      REVIEWS_TABLE_NAME         = var.reviews_table_name
      KILL_SWITCH_PARAMETER_NAME = var.kill_switch_parameter_name
    })
  }

  tags = var.tags
}

# POST /reviews/{reviewId}/findings/{findingId}/deeper: a scoped
# per-finding re-run, never the full pipeline (ADR-0023/ADR-0039). Not a
# Standard workflow: HTTP admits a job; the background worker calls AgentCore.
data "aws_iam_policy_document" "deeper_review_data_access" {
  statement {
    # ADR-0030 kill switch, checked before any paid work.
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }
  statement {
    # UpdateItem: the per-finding in-flight claim.
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    # Query: return an already-stored deeper result instead of paying for
    # a second run.
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
    resources = [var.findings_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.deeper.arn]
  }
}

resource "aws_iam_role" "deeper_review" {
  name                 = "${var.name_prefix}-deeper-review"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "deeper_review_basic_logs" {
  role       = aws_iam_role.deeper_review.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "deeper_review_data_access" {
  name   = "${var.name_prefix}-deeper-review-data-access"
  role   = aws_iam_role.deeper_review.id
  policy = data.aws_iam_policy_document.deeper_review_data_access.json
}

resource "aws_lambda_function" "deeper_review" {
  function_name    = "${var.name_prefix}-deeper-review"
  role             = aws_iam_role.deeper_review.arn
  handler          = "backend.lambdas.deeper_review.handler.handler"
  runtime          = "python3.12"
  filename         = var.deeper_review_zip_path
  source_code_hash = fileexists(var.deeper_review_zip_path) ? filebase64sha256(var.deeper_review_zip_path) : null
  # Admission and idempotent dispatch only; the model runs outside HTTP.
  timeout     = 10
  memory_size = 256

  environment {
    variables = merge(local.admission_environment, {
      REVIEWS_TABLE_NAME         = var.reviews_table_name
      FINDINGS_TABLE_NAME        = var.findings_table_name
      KILL_SWITCH_PARAMETER_NAME = var.kill_switch_parameter_name
      REPORTS_BUCKET_NAME        = var.reports_bucket_name
      DEEPER_STATE_MACHINE_ARN   = aws_sfn_state_machine.deeper.arn
    })
  }

  tags = var.tags
}

# GET /demo is the one deliberately public, unauthenticated route
# (ADR-0029, ADR-0044). It serves a precomputed reference report
# (backend/lambdas/get_demo) and never touches DynamoDB, S3, Step
# Functions, or AgentCore, so it has no pipeline cost, only normal
# static-content exposure.
resource "aws_iam_role" "get_demo" {
  name                 = "${var.name_prefix}-get-demo"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "get_demo_basic_logs" {
  role       = aws_iam_role.get_demo.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "get_demo" {
  function_name    = "${var.name_prefix}-get-demo"
  role             = aws_iam_role.get_demo.arn
  handler          = "backend.lambdas.get_demo.handler.handler"
  runtime          = "python3.12"
  filename         = var.get_demo_zip_path
  source_code_hash = fileexists(var.get_demo_zip_path) ? filebase64sha256(var.get_demo_zip_path) : null
  timeout          = 3

  environment {
    variables = { CORS_ALLOWED_ORIGINS = jsonencode(concat([var.frontend_origin], var.additional_cors_origins)) }
  }
  tags = var.tags
}

# POST /uploads (ADR-0045) issues a conditional presigned PUT so the client
# uploads its Terraform archive straight to S3, never through this Lambda or
# API Gateway. It requires a Turnstile check and counts against the upload
# limits, since it lets the caller write an object into this bucket.
data "aws_iam_policy_document" "create_upload_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/uploads/*"]
  }
  # HEAD on a missing key returns 404 only with ListBucket. Recovery must not
  # treat a genuine AccessDenied as an absent upload (AWS HeadObject contract).
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.reports_bucket_arn]
  }
}

resource "aws_iam_role" "create_upload" {
  name                 = "${var.name_prefix}-create-upload"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "create_upload_basic_logs" {
  role       = aws_iam_role.create_upload.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "create_upload_data_access" {
  name   = "${var.name_prefix}-create-upload-data-access"
  role   = aws_iam_role.create_upload.id
  policy = data.aws_iam_policy_document.create_upload_data_access.json
}

resource "aws_lambda_function" "create_upload" {
  function_name    = "${var.name_prefix}-create-upload"
  role             = aws_iam_role.create_upload.arn
  handler          = "backend.lambdas.create_upload.handler.handler"
  runtime          = "python3.12"
  filename         = var.create_upload_zip_path
  source_code_hash = fileexists(var.create_upload_zip_path) ? filebase64sha256(var.create_upload_zip_path) : null
  timeout          = 15

  environment {
    variables = merge(local.admission_environment, {
      REPORTS_BUCKET_NAME = var.reports_bucket_name
      RESERVATION_KEY     = random_password.reservation.result
    })
  }

  tags = var.tags
}

# Regional custom domain for the public REST stage, created only when a validated
# certificate is supplied (see var.certificate_arn). Regional rather than
# edge-optimized: the API lives in one region and gains nothing from an
# extra CloudFront hop.
resource "aws_apigatewayv2_domain_name" "api" {
  count       = var.certificate_arn == null ? 0 : 1
  domain_name = var.domain_name

  domain_name_configuration {
    certificate_arn = var.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = var.tags
}

# Maps the domain's root to the REST API's public stage, so
# https://api.archibrief.dev/reviews reaches .../public/reviews.
resource "aws_apigatewayv2_api_mapping" "api" {
  count       = var.certificate_arn != null && var.public_edge_enabled ? 1 : 0
  api_id      = aws_api_gateway_rest_api.public[0].id
  domain_name = aws_apigatewayv2_domain_name.api[0].id
  stage       = aws_api_gateway_stage.public[0].stage_name
}
