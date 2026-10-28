# The API: a Regional REST API whose public stage sits behind WAF, served at
# api.archibrief.dev (main.tf). Off by default in the module; the dev
# environment turns it on.
variable "public_edge_enabled" {
  type    = bool
  default = false
}

resource "aws_api_gateway_rest_api" "public" {
  count = var.public_edge_enabled ? 1 : 0
  name  = "${var.name_prefix}-public"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
  tags = var.tags
}

resource "aws_api_gateway_resource" "public_root" {
  for_each    = var.public_edge_enabled ? toset(["uploads", "reviews", "demo"]) : toset([])
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  parent_id   = aws_api_gateway_rest_api.public[0].root_resource_id
  path_part   = each.key
}

resource "aws_api_gateway_resource" "public_review" {
  count       = var.public_edge_enabled ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  parent_id   = aws_api_gateway_resource.public_root["reviews"].id
  path_part   = "{reviewId}"
}

resource "aws_api_gateway_resource" "public_children" {
  for_each    = var.public_edge_enabled ? toset(["questions", "findings"]) : toset([])
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  parent_id   = aws_api_gateway_resource.public_review[0].id
  path_part   = each.key
}

resource "aws_api_gateway_resource" "public_finding" {
  count       = var.public_edge_enabled ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  parent_id   = aws_api_gateway_resource.public_children["findings"].id
  path_part   = "{findingId}"
}

resource "aws_api_gateway_resource" "public_deeper" {
  count       = var.public_edge_enabled ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  parent_id   = aws_api_gateway_resource.public_finding[0].id
  path_part   = "deeper"
}

locals {
  public_routes = var.public_edge_enabled ? {
    upload  = { method = "POST", resource = aws_api_gateway_resource.public_root["uploads"].id, function = { invoke_arn = aws_lambda_function.create_upload.invoke_arn, function_name = aws_lambda_function.create_upload.function_name } }
    submit  = { method = "POST", resource = aws_api_gateway_resource.public_root["reviews"].id, function = { invoke_arn = aws_lambda_function.submit_review.invoke_arn, function_name = aws_lambda_function.submit_review.function_name } }
    read    = { method = "GET", resource = aws_api_gateway_resource.public_review[0].id, function = { invoke_arn = aws_lambda_function.get_review.invoke_arn, function_name = aws_lambda_function.get_review.function_name } }
    deeper  = { method = "POST", resource = aws_api_gateway_resource.public_deeper[0].id, function = { invoke_arn = aws_lambda_function.deeper_review.invoke_arn, function_name = aws_lambda_function.deeper_review.function_name } }
    ask     = { method = "POST", resource = aws_api_gateway_resource.public_children["questions"].id, function = { invoke_arn = aws_lambda_function.chat["ask_question"].invoke_arn, function_name = aws_lambda_function.chat["ask_question"].function_name } }
    history = { method = "GET", resource = aws_api_gateway_resource.public_children["questions"].id, function = { invoke_arn = aws_lambda_function.chat["list_questions"].invoke_arn, function_name = aws_lambda_function.chat["list_questions"].function_name } }
    demo    = { method = "GET", resource = aws_api_gateway_resource.public_root["demo"].id, function = { invoke_arn = aws_lambda_function.get_demo.invoke_arn, function_name = aws_lambda_function.get_demo.function_name } }
  } : {}
  public_preflight = { for key, route in local.public_routes : key => route if key != "history" }
}

# No authorizer: every handler checks PUBLIC_ACCESS_ENABLED (and the chat
# flag) itself, and refuses anonymous callers while it is off. A
# header-based authorizer would also reject visitors who send no header
# before the handler runs.
resource "aws_api_gateway_method" "public" {
  for_each      = local.public_routes
  rest_api_id   = aws_api_gateway_rest_api.public[0].id
  resource_id   = each.value.resource
  http_method   = each.value.method
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "public" {
  for_each                = local.public_routes
  rest_api_id             = aws_api_gateway_rest_api.public[0].id
  resource_id             = each.value.resource
  http_method             = aws_api_gateway_method.public[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = each.value.function.invoke_arn
  timeout_milliseconds    = 29000
}

resource "aws_lambda_permission" "public" {
  for_each      = local.public_routes
  statement_id  = "AllowPublicREST-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function.function_name
  principal     = "apigateway.amazonaws.com"
  # No other stage can invoke paid functions through this permission.
  source_arn = "${aws_api_gateway_rest_api.public[0].execution_arn}/public/${each.value.method}/*"
}

resource "aws_api_gateway_method" "preflight" {
  for_each      = local.public_preflight
  rest_api_id   = aws_api_gateway_rest_api.public[0].id
  resource_id   = each.value.resource
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "preflight" {
  for_each                = local.public_preflight
  rest_api_id             = aws_api_gateway_rest_api.public[0].id
  resource_id             = each.value.resource
  http_method             = aws_api_gateway_method.preflight[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = each.value.function.invoke_arn
}

resource "aws_lambda_permission" "preflight" {
  for_each      = local.public_preflight
  statement_id  = "AllowPublicPreflight-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.public[0].execution_arn}/public/OPTIONS/*"
}

# Errors API Gateway answers itself (throttling, missing route, integration
# failure) carry no CORS headers by default, so the browser would report a
# CORS failure instead of the real status. These carry no review data, so
# echoing the caller's Origin is safe.
resource "aws_api_gateway_gateway_response" "public" {
  for_each      = var.public_edge_enabled ? toset(["DEFAULT_4XX", "DEFAULT_5XX"]) : toset([])
  rest_api_id   = aws_api_gateway_rest_api.public[0].id
  response_type = each.key
  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin" = "method.request.header.origin"
    "gatewayresponse.header.Vary"                        = "'Origin'"
  }
  # AWS restores this default template whenever it's left out, and the
  # deployment trigger below hashes these responses, so it's declared to
  # keep that hash stable during apply.
  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }
}

resource "aws_api_gateway_deployment" "public" {
  count       = var.public_edge_enabled ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  triggers = {
    routes = sha1(jsonencode([aws_api_gateway_method.public, aws_api_gateway_integration.public, aws_api_gateway_integration.preflight, aws_api_gateway_gateway_response.public]))
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "public" {
  count         = var.public_edge_enabled ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.public[0].id
  deployment_id = aws_api_gateway_deployment.public[0].id
  stage_name    = "public"
  tags          = var.tags
}

resource "aws_api_gateway_method_settings" "public" {
  count       = var.public_edge_enabled ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  stage_name  = aws_api_gateway_stage.public[0].stage_name
  method_path = "*/*"
  settings {
    throttling_burst_limit = var.throttling_burst_limit
    throttling_rate_limit  = var.throttling_rate_limit
    data_trace_enabled     = false
    metrics_enabled        = true
  }
}

# Per-route quotas below the stage-wide one: GET /demo needs no capability,
# and each chat question is a paid model call (ADR-0050 §5). The daily
# budgets are the real stop; these keep one client from spending them in
# seconds.
resource "aws_api_gateway_method_settings" "route" {
  for_each = var.public_edge_enabled ? {
    "demo/GET" = {
      burst = var.demo_throttling_burst_limit
      rate  = var.demo_throttling_rate_limit
    }
    "reviews/{reviewId}/questions/POST" = {
      burst = var.chat_throttling_burst_limit
      rate  = var.chat_throttling_rate_limit
    }
  } : {}
  rest_api_id = aws_api_gateway_rest_api.public[0].id
  stage_name  = aws_api_gateway_stage.public[0].stage_name
  method_path = each.key
  settings {
    throttling_burst_limit = each.value.burst
    throttling_rate_limit  = each.value.rate
    data_trace_enabled     = false
    metrics_enabled        = true
  }
}

resource "aws_wafv2_web_acl" "public" {
  count = var.public_edge_enabled ? 1 : 0
  name  = "${var.name_prefix}-public"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "body-bound"
    priority = 1
    action {
      block {}
    }
    statement {
      size_constraint_statement {
        comparison_operator = "GT"
        size                = 16384
        field_to_match {
          body {
            oversize_handling = "MATCH"
          }
        }
        text_transformation {
          priority = 0
          type     = "NONE"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "body-bound"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "per-ip-rate"
    priority = 2
    action {
      block {
        # 429, so the frontend can say "too many requests" rather than "forbidden".
        custom_response {
          response_code = 429
        }
      }
    }
    statement {
      rate_based_statement {
        limit              = 300
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "per-ip-rate"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "common-threats"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common-threats"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "public-api"
    sampled_requests_enabled   = false
  }
  tags = var.tags
}

resource "aws_wafv2_web_acl_association" "public" {
  count        = var.public_edge_enabled ? 1 : 0
  resource_arn = aws_api_gateway_stage.public[0].arn
  web_acl_arn  = aws_wafv2_web_acl.public[0].arn
}
