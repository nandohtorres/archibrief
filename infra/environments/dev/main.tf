# Dev environment root: wires infra/modules together. No user accounts
# (ADR-0044) and no auth module; the API is gated by a single pre-shared
# admin credential generated inside the api-gateway module.

provider "aws" {
  region = var.region
}

# Custom domain. One cert covers all three names: CloudFront requires
# us-east-1, and API Gateway's regional custom domain needs the cert in
# the API's region, which is also us-east-1 here, so no provider alias is
# needed. DNS validation: Cloudflare is the DNS host, not Route53, so the
# validation CNAMEs (acm_validation_records output) and the final CNAME
# targets (frontend_dns_target/api_dns_target outputs) are added manually
# in the Cloudflare dashboard. See this environment's README for the
# two-phase apply; otherwise the validation resource below waits up to
# its 45-minute default timeout for records that don't exist.
resource "aws_acm_certificate" "site" {
  domain_name = var.domain
  subject_alternative_names = [
    "www.${var.domain}",
    "api.${var.domain}",
  ]
  validation_method = "DNS"
  tags              = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "site" {
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_name]
}

module "s3" {
  source          = "../../modules/s3"
  bucket_name     = "${var.name_prefix}-${var.environment}-source-of-truth"
  frontend_origin = "https://${module.frontend_hosting.cloudfront_domain_name}"
  # Same list as module.api_gateway: the browser calls the API, then POSTs
  # the archive straight to this bucket from the same page origin.
  additional_cors_origins = ["https://${var.domain}", "https://www.${var.domain}"]
  tags                    = var.tags
}

module "s3_vectors" {
  source             = "../../modules/s3-vectors"
  vector_bucket_name = "${var.name_prefix}-${var.environment}-kb"
  index_name         = "${var.name_prefix}-${var.environment}-kb-index"
  dimension          = var.embedding_dimension
  distance_metric    = var.embedding_distance_metric
  tags               = var.tags
}

module "dynamodb" {
  source       = "../../modules/dynamodb"
  table_prefix = "${var.name_prefix}-${var.environment}"
  tags         = var.tags
}

module "iam" {
  source                   = "../../modules/iam"
  name_prefix              = "${var.name_prefix}-${var.environment}"
  github_oidc_provider_arn = var.github_oidc_provider_arn
  github_repo              = var.github_repo
  tags                     = var.tags
}

module "guardrails" {
  source      = "../../modules/guardrails"
  name_prefix = "${var.name_prefix}-${var.environment}"
  tags        = var.tags
}

module "kill_switch" {
  source      = "../../modules/kill-switch"
  name_prefix = "${var.name_prefix}-${var.environment}"
  tags        = var.tags
}

module "agentcore_runtime" {
  source                   = "../../modules/agentcore-runtime"
  name_prefix              = "${var.name_prefix}-${var.environment}"
  agent_runtime_zip_path   = var.agentcore_runtime_zip_path
  permissions_boundary_arn = module.iam.runtime_permissions_boundary_arn
  guardrail_id             = module.guardrails.guardrail_id
  guardrail_version        = module.guardrails.guardrail_version
  vector_bucket_name       = module.s3_vectors.vector_bucket_name
  vector_index_name        = module.s3_vectors.index_name
  tags                     = var.tags
}

module "step_functions_lambda" {
  source              = "../../modules/step-functions-lambda"
  name_prefix         = "${var.name_prefix}-${var.environment}"
  lambda_zip_paths    = var.lambda_zip_paths
  reports_bucket_arn  = module.s3.bucket_arn
  reports_bucket_name = module.s3.bucket_id
  reviews_table_arn   = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.reviews_table_name}"
  reviews_table_name  = module.dynamodb.reviews_table_name
  audit_table_arn     = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.audit_log_table_name}"
  # Resolvable only once the AgentCore Runtime package exists (see
  # modules/agentcore-runtime's agent_runtime_zip_path).
  agentcore_runtime_arn      = module.agentcore_runtime.agent_runtime_arn
  permissions_boundary_arn   = module.iam.runtime_permissions_boundary_arn
  guardrail_id               = module.guardrails.guardrail_id
  guardrail_version          = module.guardrails.guardrail_version
  kill_switch_parameter_name = module.kill_switch.parameter_name
  kill_switch_parameter_arn  = module.kill_switch.parameter_arn
  usage_counters_table_name  = module.dynamodb.usage_counters_table_name
  usage_counters_table_arn   = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.usage_counters_table_name}"
  tags                       = var.tags
}

module "frontend_hosting" {
  source      = "../../modules/frontend-hosting"
  name_prefix = "${var.name_prefix}-${var.environment}"
  bucket_name = "${var.name_prefix}-${var.environment}-frontend"
  # Space-separated: CSP connect-src accepts multiple source expressions.
  # Includes the custom API domain alongside the wildcard execute-api
  # pattern, since the frontend may be built with either as
  # NEXT_PUBLIC_API_BASE_URL.
  api_origin_pattern = "https://*.execute-api.${var.region}.amazonaws.com https://api.${var.domain}"
  aliases            = [var.domain, "www.${var.domain}"]
  certificate_arn    = aws_acm_certificate_validation.site.certificate_arn
  tags               = var.tags
}

module "api_gateway" {
  verified_public_api_id          = var.verified_public_api_id
  public_edge_enabled             = var.public_edge_enabled
  public_access_enabled           = var.public_access_enabled
  chat_public_enabled             = var.public_access_enabled
  turnstile_secret_parameter_arn  = var.turnstile_secret_parameter_arn
  turnstile_secret_parameter_name = var.turnstile_secret_parameter_name
  turnstile_hostname              = var.domain
  source                          = "../../modules/api-gateway"
  name_prefix                     = "${var.name_prefix}-${var.environment}"
  state_machine_arn               = module.step_functions_lambda.state_machine_arn
  kill_switch_parameter_name      = module.kill_switch.parameter_name
  kill_switch_parameter_arn       = module.kill_switch.parameter_arn
  domain_name                     = "api.${var.domain}"
  certificate_arn                 = aws_acm_certificate_validation.site.certificate_arn
  frontend_origin                 = "https://${module.frontend_hosting.cloudfront_domain_name}"
  additional_cors_origins         = ["https://${var.domain}", "https://www.${var.domain}"]
  admin_authorizer_zip_path       = var.admin_authorizer_zip_path
  get_review_zip_path             = var.get_review_zip_path
  clarify_review_zip_path         = var.clarify_review_zip_path
  deeper_review_zip_path          = var.deeper_review_zip_path
  get_demo_zip_path               = var.get_demo_zip_path
  create_upload_zip_path          = var.create_upload_zip_path
  reviews_table_name              = module.dynamodb.reviews_table_name
  reviews_table_arn               = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.reviews_table_name}"
  findings_table_name             = module.dynamodb.findings_table_name
  findings_table_arn              = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.findings_table_name}"
  reports_bucket_name             = module.s3.bucket_id
  reports_bucket_arn              = module.s3.bucket_arn
  agentcore_runtime_arn           = module.agentcore_runtime.agent_runtime_arn
  permissions_boundary_arn        = module.iam.runtime_permissions_boundary_arn

  # Report chat (ADR-0050).
  ask_question_zip_path            = var.ask_question_zip_path
  list_questions_zip_path          = var.list_questions_zip_path
  review_questions_table_name      = module.dynamodb.review_questions_table_name
  review_questions_table_arn       = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.review_questions_table_name}"
  usage_counters_table_name        = module.dynamodb.usage_counters_table_name
  usage_counters_table_arn         = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.usage_counters_table_name}"
  chat_guardrail_id                = module.guardrails.chat_guardrail_id
  chat_guardrail_version           = module.guardrails.chat_guardrail_version
  chat_guardrail_arn               = module.guardrails.chat_guardrail_arn
  chat_grounding_guardrail_id      = module.guardrails.chat_grounding_guardrail_id
  chat_grounding_guardrail_version = module.guardrails.chat_grounding_guardrail_version
  chat_grounding_guardrail_arn     = module.guardrails.chat_grounding_guardrail_arn
  vector_bucket_name               = module.s3_vectors.vector_bucket_name
  vector_index_name                = module.s3_vectors.index_name
  chat_alarms_enabled              = var.chat_alarms_enabled
  alarm_topic_arn                  = module.cost_controls.budget_alerts_topic_arn

  tags = var.tags
}

module "cost_controls" {
  source             = "../../modules/cost-controls"
  name_prefix        = "${var.name_prefix}-${var.environment}"
  monthly_budget_usd = var.monthly_budget_usd
  alert_email        = var.alert_email
  tags               = var.tags
}
