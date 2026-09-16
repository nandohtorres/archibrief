# Terraform module: iam
# Scope: deployment/bootstrap roles and cross-service policies ONLY (the
# CI/CD deploy role, the admin break-glass grant procedure per ADR-0037).
# Per-Lambda execution roles do NOT belong here — each Lambda's
# least-privilege execution role is defined in
# infra/modules/step-functions-lambda, the same module as the Lambda
# itself (ADR-0021) — never a shared/generic role.
#
# github_oidc_provider_arn is null until AWS account bootstrap registers
# the GitHub Actions OIDC provider — this module's deploy role is not
# created until that exists (count-gated below).

data "aws_iam_policy_document" "deploy_role_trust" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "ci_deploy" {
  count              = var.github_oidc_provider_arn == null ? 0 : 1
  name               = "${var.name_prefix}-ci-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_role_trust[0].json
  tags               = var.tags
}

# The admin app-role (ADR-0037) is granted out-of-band via a break-glass
# CLI/console procedure, never an in-app endpoint — this group exists so
# that procedure has a concrete IAM principal to attach a scoped policy
# to, not an automated self-service grant path.
resource "aws_iam_group" "admin_break_glass" {
  name = "${var.name_prefix}-admin-break-glass"
}

# Permissions boundary for every archibrief-dev-* role that gets passed
# to a runtime service principal (lambda.amazonaws.com,
# states.amazonaws.com, apigateway.amazonaws.com) — the actual
# enforcement for the privilege-escalation gap flagged and deliberately
# deferred in Work-Project-Issues-Log.md (2026-09-09, "deploy role has
# no IAM permissions boundary"): the deploy identity can create/modify
# these roles and attach policies to them via PutRolePolicy/
# AttachRolePolicy with no boundary today. Once every such role in
# deploy-role-policy.json's iam:CreateRole condition + each module's
# `permissions_boundary` argument enforce this boundary, IAM caps the
# role's EFFECTIVE permissions to the intersection of its own policy and
# this boundary — so even a mistakenly (or maliciously) over-broad
# policy attached to one of these roles can't grant it more than what's
# listed here. Deliberately does NOT apply to ci_deploy above: that role
# is assumed directly via GitHub Actions OIDC, not passed to a runtime
# service principal, and legitimately needs the same broad
# infrastructure-management permissions as the deploy identity itself —
# a different vector than the one this finding described.
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "runtime_permissions_boundary" {
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
    # scoping in IAM — same as the identity policies that already use
    # them (step-functions-lambda's state_machine_invoke document).
    resources = ["*"]
  }

  # Explicit, self-documenting escalation blocklist. Technically
  # redundant with the enumerated Allow list above (an IAM boundary
  # defaults to deny for anything not explicitly allowed), but kept
  # explicit so a future careless wildcard Allow added above can't
  # silently reopen the exact gap this boundary exists to close.
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
  description = "Permissions boundary for archibrief-dev-* roles passed to Lambda/Step Functions/API Gateway service principals. See Work-Project-Issues-Log.md, 2026-09-09."
  policy      = data.aws_iam_policy_document.runtime_permissions_boundary.json
  tags        = var.tags
}
