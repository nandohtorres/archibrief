# A guardrail that denies everything. It grants nothing.
resource "aws_iam_policy" "deny_all_guardrail" {
  name = "deny-all-guardrail"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Deny", Action = "*", Resource = "*" }]
  })
}

# Allow with NotAction: every action except IAM and Organizations, everywhere.
resource "aws_iam_policy" "almost_admin" {
  name = "almost-admin"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", NotAction = ["iam:*", "organizations:*"], Resource = "*" }]
  })
}

data "aws_iam_policy_document" "almost_admin_doc" {
  statement {
    effect      = "Allow"
    not_actions = ["iam:*", "organizations:*"]
    resources   = ["*"]
  }
}

resource "aws_iam_policy" "almost_admin_doc" {
  name   = "almost-admin-doc"
  policy = data.aws_iam_policy_document.almost_admin_doc.json
}

# Allow with NotResource: every S3 action on every bucket but one.
resource "aws_iam_policy" "s3_everything_else" {
  name = "s3-everything-else"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "s3:*", NotResource = "arn:aws:s3:::audit-log/*" }]
  })
}

# Wildcard content, attached to no user, group or role.
resource "aws_iam_policy" "orphan_wildcard" {
  name = "orphan-wildcard"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "s3:*", Resource = "*" }]
  })
}
