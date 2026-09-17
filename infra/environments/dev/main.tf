# Dev environment root — wires infra/modules together. No user accounts
# (ADR-0044) — no auth module; the API is gated by a single pre-shared
# admin credential generated inside the api-gateway module. Several
# module inputs (GitHub OIDC provider, AgentCore Runtime ARN, Lambda
# deployment packages) are placeholders until AWS account/IAM bootstrap
# work not yet done, marked TODO(account-setup) at their source.

provider "aws" {
  region = var.region
}

module "s3" {
  source      = "../../modules/s3"
  bucket_name = "${var.name_prefix}-${var.environment}-source-of-truth"
  tags        = var.tags
}

module "s3_vectors" {
  source                        = "../../modules/s3-vectors"
  vector_bucket_name            = "${var.name_prefix}-${var.environment}-kb"
  index_name                    = "${var.name_prefix}-${var.environment}-kb-index"
  dimension                     = var.embedding_dimension
  distance_metric                = var.embedding_distance_metric
  tags                           = var.tags
}

module "dynamodb" {
  source       = "../../modules/dynamodb"
  table_prefix = "${var.name_prefix}-${var.environment}"
  tags         = var.tags
}

module "iam" {
  source                    = "../../modules/iam"
  name_prefix               = "${var.name_prefix}-${var.environment}"
  github_oidc_provider_arn  = var.github_oidc_provider_arn
  github_repo               = var.github_repo
  tags                      = var.tags
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
  source                    = "../../modules/agentcore-runtime"
  name_prefix               = "${var.name_prefix}-${var.environment}"
  agent_runtime_zip_path    = var.agentcore_runtime_zip_path
  permissions_boundary_arn  = module.iam.runtime_permissions_boundary_arn
  guardrail_id              = module.guardrails.guardrail_id
  guardrail_version         = module.guardrails.guardrail_version
  vector_bucket_name        = module.s3_vectors.vector_bucket_name
  vector_index_name         = module.s3_vectors.index_name
  tags                      = var.tags
}

module "step_functions_lambda" {
  source                    = "../../modules/step-functions-lambda"
  name_prefix                = "${var.name_prefix}-${var.environment}"
  lambda_zip_paths           = var.lambda_zip_paths
  reports_bucket_arn         = module.s3.bucket_arn
  reports_bucket_name        = module.s3.bucket_id
  reviews_table_arn          = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.reviews_table_name}"
  reviews_table_name         = module.dynamodb.reviews_table_name
  audit_table_arn            = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.audit_log_table_name}"
  # Replaced the raw placeholder var with the real module output
  # (2026-09-16) — module.agentcore_runtime.agent_runtime_arn is only
  # actually resolvable once modules/agentcore-runtime's own real
  # prerequisite (a packaged ZIP artifact — see that module's
  # agent_runtime_zip_path TODO) exists; until then this still won't
  # apply cleanly, same documented deferral as every other TODO(account-setup)
  # placeholder in this environment, not a new problem this change causes.
  agentcore_runtime_arn      = module.agentcore_runtime.agent_runtime_arn
  permissions_boundary_arn   = module.iam.runtime_permissions_boundary_arn
  guardrail_id               = module.guardrails.guardrail_id
  guardrail_version           = module.guardrails.guardrail_version
  kill_switch_parameter_name = module.kill_switch.parameter_name
  kill_switch_parameter_arn  = module.kill_switch.parameter_arn
  tags                       = var.tags
}

module "frontend_hosting" {
  source      = "../../modules/frontend-hosting"
  name_prefix = "${var.name_prefix}-${var.environment}"
  bucket_name = "${var.name_prefix}-${var.environment}-frontend"
  tags        = var.tags
}

module "api_gateway" {
  source                       = "../../modules/api-gateway"
  name_prefix                   = "${var.name_prefix}-${var.environment}"
  state_machine_arn             = module.step_functions_lambda.state_machine_arn
  domain_name                   = "api.${var.domain}"
  admin_authorizer_zip_path     = var.admin_authorizer_zip_path
  permissions_boundary_arn      = module.iam.runtime_permissions_boundary_arn
  tags                           = var.tags
}

module "cost_controls" {
  source                 = "../../modules/cost-controls"
  name_prefix             = "${var.name_prefix}-${var.environment}"
  monthly_budget_usd      = var.monthly_budget_usd
  alert_email             = var.alert_email
  tags                   = var.tags
}
