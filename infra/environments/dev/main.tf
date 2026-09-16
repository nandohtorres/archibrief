# Dev environment root — wires infra/modules together.
# Cannot be applied until AWS account/IAM bootstrap exists (see
# Work-Project-Deployment-Roadmap.md) — provider auth, account_id, and
# several module inputs (SES ARN, GitHub OIDC provider, AgentCore Runtime
# ARN, Lambda deployment packages) are placeholders until then, marked
# TODO(account-setup) at their source.

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

module "auth" {
  source              = "../../modules/auth"
  user_pool_name      = "${var.name_prefix}-${var.environment}"
  domain              = var.domain
  callback_urls       = ["https://${var.domain}/auth/callback"]
  logout_urls         = ["https://${var.domain}/"]
  ses_source_arn      = var.ses_source_arn
  from_email_address  = "no-reply@${var.domain}"
  tags                = var.tags
}

module "iam" {
  source                    = "../../modules/iam"
  name_prefix               = "${var.name_prefix}-${var.environment}"
  github_oidc_provider_arn  = var.github_oidc_provider_arn
  github_repo               = var.github_repo
  tags                      = var.tags
}

module "step_functions_lambda" {
  source                  = "../../modules/step-functions-lambda"
  name_prefix              = "${var.name_prefix}-${var.environment}"
  lambda_zip_paths         = var.lambda_zip_paths
  reports_bucket_arn       = module.s3.bucket_arn
  reviews_table_arn        = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.reviews_table_name}"
  audit_table_arn          = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/${module.dynamodb.audit_log_table_name}"
  agentcore_runtime_arn    = var.agentcore_runtime_arn
  tags                     = var.tags
}

module "api_gateway" {
  source                       = "../../modules/api-gateway"
  name_prefix                   = "${var.name_prefix}-${var.environment}"
  cognito_user_pool_id          = module.auth.user_pool_id
  cognito_user_pool_client_id   = module.auth.user_pool_client_id
  state_machine_arn             = module.step_functions_lambda.state_machine_arn
  domain_name                   = "api.${var.domain}"
  tags                           = var.tags
}
