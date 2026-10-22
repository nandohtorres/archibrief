# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# The same full-admin statement written three ways. Equivalent policies
# must get equivalent conclusions.
resource "aws_iam_policy" "admin_heredoc" {
  name   = "admin-heredoc"
  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": "*", "Resource": "*"}
  ]
}
POLICY
}

resource "aws_iam_policy" "admin_jsonencode" {
  name = "admin-jsonencode"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }]
  })
}

data "aws_iam_policy_document" "admin_document" {
  statement {
    effect    = "Allow"
    actions   = ["*"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "admin_document" {
  name   = "admin-document"
  policy = data.aws_iam_policy_document.admin_document.json
}
