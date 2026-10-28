# Terraform module: iam
# Scope: deployment/bootstrap roles and cross-service policies only (the
# CI/CD deploy role, the admin break-glass grant procedure per ADR-0037).
# Per-Lambda execution roles do not belong here; each one is defined in
# the same module as its Lambda (ADR-0021), never a shared role.
#
# Frontend delivery only; infrastructure remains an owner-operated deploy.
# The production environment must restrict deployment branches to master.
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # IAM verifies GitHub through its trusted CA library; no pinned thumbprint.
  tags = var.tags
}

locals {
  ci_deploy_enabled     = var.create_github_oidc_provider || var.github_oidc_provider_arn != null
  github_provider_arn   = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.github_oidc_provider_arn
  github_subject_prefix = coalesce(var.github_oidc_subject_prefix, "repo:${var.github_repo}")
}

data "aws_iam_policy_document" "deploy_role_trust" {
  count = local.ci_deploy_enabled ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.github_subject_prefix}:environment:production"]
    }
  }
}

resource "aws_iam_role" "ci_deploy" {
  count              = local.ci_deploy_enabled ? 1 : 0
  name               = "${var.name_prefix}-ci-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_role_trust[0].json
  tags               = var.tags
}

data "aws_iam_policy_document" "frontend_deploy" {
  count = local.ci_deploy_enabled ? 1 : 0

  statement {
    sid       = "ListFrontendBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.frontend_bucket_arn]
  }
  statement {
    sid       = "PublishFrontendObjects"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.frontend_bucket_arn}/*"]
  }
  statement {
    sid       = "InvalidateFrontendDistribution"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [var.frontend_distribution_arn]
  }
}

resource "aws_iam_role_policy" "frontend_deploy" {
  count  = local.ci_deploy_enabled ? 1 : 0
  name   = "frontend-deploy"
  role   = aws_iam_role.ci_deploy[0].id
  policy = data.aws_iam_policy_document.frontend_deploy[0].json
}

# The admin app-role (ADR-0037) is granted out-of-band via a break-glass
# CLI/console procedure, never an in-app endpoint. This group gives that
# procedure a concrete IAM principal to attach a scoped policy to; it is
# not an automated self-service grant path.
resource "aws_iam_group" "admin_break_glass" {
  name = "${var.name_prefix}-admin-break-glass"
}

# Permissions boundary for every archibrief-dev-* role that gets passed
# to a runtime service principal (lambda.amazonaws.com,
# states.amazonaws.com, apigateway.amazonaws.com). The deploy identity
# can create these roles and attach policies to them, so without a
# boundary it could escalate privileges through them. With
# deploy-role-policy.json's iam:CreateRole condition and each module's
# `permissions_boundary` argument enforcing this boundary, a role's
# effective permissions are the intersection of its own policy and this
# boundary, so even an over-broad policy attached to one of these roles
# can't grant more than what is listed here. Not applied to ci_deploy
# above: that role is assumed directly through GitHub Actions OIDC, not
# passed to a service principal. It only publishes the frontend bucket
# and invalidates its distribution.
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "runtime_permissions_boundary" {
  statement {
    sid       = "AllowServiceMediatedStorageEncryption"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["arn:aws:kms:*:${data.aws_caller_identity.current.account_id}:key/*"]
    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values   = ["s3.*.amazonaws.com", "ssm.*.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
  statement {
    sid    = "AllowProjectDataAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3vectors:GetIndex",
      "s3vectors:QueryVectors",
      "s3vectors:GetVectors",
    ]
    resources = [
      "arn:aws:dynamodb:*:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-*",
      "arn:aws:dynamodb:*:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-*/index/*",
      "arn:aws:s3:::${var.name_prefix}-*",
      "arn:aws:s3:::${var.name_prefix}-*/*",
      "arn:aws:s3vectors:*:${data.aws_caller_identity.current.account_id}:bucket/${var.name_prefix}-*",
      "arn:aws:s3vectors:*:${data.aws_caller_identity.current.account_id}:bucket/${var.name_prefix}-*/index/*",
    ]
  }

  statement {
    sid       = "AllowProjectLambdaInvoke"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:${var.name_prefix}-*"]
  }

  statement {
    sid       = "AllowProjectStateMachineStart"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = ["arn:aws:states:*:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name_prefix}-*"]
  }

  statement {
    sid       = "AllowAgentCoreInvoke"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = ["arn:aws:bedrock-agentcore:*:${data.aws_caller_identity.current.account_id}:runtime/*"]
  }

  statement {
    sid       = "AllowGuardrailsApply"
    effect    = "Allow"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = ["arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:guardrail/*"]
  }

  # Every model a runtime role calls must also be allowed here, or the
  # boundary intersection silently blocks the call even when the role's
  # identity policy grants it. Converse is authorized by
  # bedrock:InvokeModel (there is no separate Converse action);
  # GetInferenceProfile is needed for the cross-region inference profile
  # ARNs. Scoped to specific models rather than all of Bedrock, matching
  # BedrockReasoningInvoke in deploy-role-policy.example.json.
  statement {
    sid    = "AllowBedrockReasoningInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:GetInferenceProfile",
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-5",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-5",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-4-6",
      # The report chat's default model (ADR-0050). Only the chat Lambda's
      # own role grants it; the boundary just has to allow it.
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      # Titan V2 embeddings (ADR-0035), matching the AgentCore execution
      # role's grant in modules/agentcore-runtime/main.tf.
      "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0",
    ]
  }

  # The state machine's CheckKillSwitch task (an ssm:getParameter SDK
  # integration) and the kill-switch checks in the API Lambdas need this.
  # Without it the intersection is empty and every execution fails with
  # AccessDenied before Ingest runs.
  statement {
    sid     = "AllowKillSwitchRead"
    effect  = "Allow"
    actions = ["ssm:GetParameter"]
    # The kill-switch parameter is named "/${name_prefix}/kill-switch"
    # (slash-delimited, see infra/modules/kill-switch/main.tf), unlike the
    # hyphen-delimited "${name_prefix}-*" resources elsewhere in this
    # boundary, so the pattern uses a slash.
    resources = ["arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/*"]
  }

  # The cost-controls spend-stop Lambda turns the kill switch on when the
  # monthly budget's stop tier fires. Only that one parameter is writable.
  statement {
    sid       = "AllowKillSwitchTrip"
    effect    = "Allow"
    actions   = ["ssm:PutParameter"]
    resources = ["arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/kill-switch"]
  }

  # clarify_review (infra/modules/api-gateway/main.tf) calls
  # SendTaskSuccess/SendTaskFailure to resume a review paused at
  # StoreClarificationToken. Resource "*" because these actions identify
  # the paused task by token, not by state machine ARN.
  statement {
    sid       = "AllowClarificationTaskTokenCompletion"
    effect    = "Allow"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowLogging"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    # Log-delivery/resource-policy actions don't support resource-level
    # scoping in IAM, the same as in the identity policies that use them
    # (step-functions-lambda's state_machine_invoke document).
    resources = ["*"]
  }

  # Explicit escalation blocklist. Redundant with the enumerated Allow
  # list above (a boundary denies anything not allowed), but it keeps a
  # future wildcard Allow from silently reopening the gap this boundary
  # exists to close.
  statement {
    sid    = "DenyEscalationVectors"
    effect = "Deny"
    actions = [
      "iam:*",
      "organizations:*",
      "account:*",
      "sts:AssumeRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "runtime_permissions_boundary" {
  name        = "${var.name_prefix}-runtime-boundary"
  description = "Permissions boundary for archibrief-dev-* roles passed to Lambda/Step Functions/API Gateway service principals."
  policy      = data.aws_iam_policy_document.runtime_permissions_boundary.json
  tags        = var.tags

  # A new description forces a new policy, and every runtime role uses this
  # one as its boundary. The deployed policy keeps its original description.
  lifecycle {
    ignore_changes = [description]
  }
}
