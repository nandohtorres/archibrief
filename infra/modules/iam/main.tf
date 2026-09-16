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
