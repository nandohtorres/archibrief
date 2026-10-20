# The Lambda log groups were created by Lambda on each function's first run,
# before Terraform managed them. These blocks adopt them so the modules can
# set retention without deleting or recreating them. They're a no-op once the
# groups are in state, and can be removed after the first apply.
locals {
  lambda_log_prefix = "/aws/lambda/${var.name_prefix}-${var.environment}"

  api_lambda_log_groups = {
    admin_authorizer = "admin-authorizer"
    get_review       = "get-review"
    clarify_review   = "clarify-review"
    deeper_review    = "deeper-review"
    get_demo         = "get-demo"
    create_upload    = "create-upload"
  }

  # Keys match local.lambda_specs in modules/step-functions-lambda, whose
  # function names reuse the key (underscores included).
  pipeline_lambda_log_groups = {
    ingest                    = "ingest"
    rule_engine               = "rule_engine"
    validate                  = "validate"
    audit                     = "audit"
    finalize                  = "finalize"
    store_clarification_token = "store_clarification_token"
    scan                      = "scan"
    mark_review_failed        = "mark-review-failed"
  }
}

import {
  for_each = local.api_lambda_log_groups
  to       = module.api_gateway.aws_cloudwatch_log_group.lambda[each.key]
  id       = "${local.lambda_log_prefix}-${each.value}"
}

import {
  for_each = local.pipeline_lambda_log_groups
  to       = module.step_functions_lambda.aws_cloudwatch_log_group.lambda[each.key]
  id       = "${local.lambda_log_prefix}-${each.value}"
}
