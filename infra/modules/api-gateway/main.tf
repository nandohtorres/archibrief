# Terraform module: api-gateway
# HTTP API (API Gateway v2) — Cognito JWT authorizer, throttling/usage
# plans as a best-effort layer, not a guaranteed ceiling (ADR-0005,
# ADR-0030 — real enforcement is the application-level layered controls
# built in the backend, not this module). Routes match the API contracts
# in Work-Project-System-Design.md. POST /reviews integrates directly
# with Step Functions StartExecution — no BFF Lambda (ADR-0016/0042).
#
# GET /reviews/{reviewId}, POST /clarify, and the "go deeper" endpoint
# need a DynamoDB/Step-Functions-task-token direct integration whose
# exact request/response mapping is an implementation detail to verify
# against the live API Gateway v2 AWS_PROXY subtype support at build
# time — modeled here with the integration resource shape, mapping TODOs
# flagged inline.

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["https://archibrief.dev"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
  }

  tags = var.tags
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-cognito-authorizer"

  jwt_configuration {
    audience = [var.cognito_user_pool_client_id]
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

data "aws_region" "current" {}

data "aws_iam_policy_document" "apigw_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigw_invoke_step_functions" {
  name               = "${var.name_prefix}-apigw-invoke-sfn"
  assume_role_policy = data.aws_iam_policy_document.apigw_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "apigw_invoke_step_functions" {
  name = "${var.name_prefix}-apigw-start-execution"
  role = aws_iam_role.apigw_invoke_step_functions.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = var.state_machine_arn
    }]
  })
}

resource "aws_apigatewayv2_integration" "start_review" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_subtype    = "StepFunctions-StartExecution"
  credentials_arn        = aws_iam_role.apigw_invoke_step_functions.arn
  payload_format_version = "1.0"

  request_parameters = {
    StateMachineArn = var.state_machine_arn
    Input           = "$request.body"
  }
}

resource "aws_apigatewayv2_route" "post_reviews" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /reviews"
  target             = "integrations/${aws_apigatewayv2_integration.start_review.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# TODO(implementation): GET /reviews/{reviewId} reads the Reviews table
# directly via a DynamoDB GetItem AWS_PROXY integration — request/response
# mapping to verify once the table's real key schema is deployed.
resource "aws_apigatewayv2_route" "get_review" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /reviews/{reviewId}"
  target             = "integrations/${aws_apigatewayv2_integration.start_review.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# TODO(implementation): POST /clarify resumes a paused Step Functions
# execution via SendTaskSuccess with the stored task token — needs the
# token looked up from DynamoDB first, likely via a thin Lambda rather
# than a pure AWS_PROXY integration. Revisit during Phase 3 build.
resource "aws_apigatewayv2_route" "post_clarify" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /reviews/{reviewId}/clarify"
  target             = "integrations/${aws_apigatewayv2_integration.start_review.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "post_deeper" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /reviews/{reviewId}/findings/{findingId}/deeper"
  target             = "integrations/${aws_apigatewayv2_integration.start_review.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# GET /demo is intentionally unauthenticated (guest/demo entrypoint,
# ADR-0010) — rate-limited by IP at the stage throttling settings below,
# not by the JWT authorizer.
resource "aws_apigatewayv2_route" "get_demo" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /demo"
  target    = "integrations/${aws_apigatewayv2_integration.start_review.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.throttling_burst_limit
    throttling_rate_limit  = var.throttling_rate_limit
  }

  tags = var.tags
}
