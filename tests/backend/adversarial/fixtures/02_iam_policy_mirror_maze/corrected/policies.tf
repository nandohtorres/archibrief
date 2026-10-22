# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_iam_policy" "reports_reader" {
  name = "reports-reader"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["s3:GetObject"], Resource = "arn:aws:s3:::maze-reports/*" }]
  })
}

data "aws_iam_policy_document" "reports_reader_doc" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::maze-reports/*"]
  }
}

resource "aws_iam_policy" "reports_reader_doc" {
  name   = "reports-reader-doc"
  policy = data.aws_iam_policy_document.reports_reader_doc.json
}

resource "aws_iam_policy" "deny_all_guardrail" {
  name = "deny-all-guardrail"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Deny", Action = "*", Resource = "*" }]
  })
}

resource "aws_iam_role" "scoped_worker" {
  name = "scoped-worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scoped_worker_reader" {
  role       = aws_iam_role.scoped_worker.name
  policy_arn = aws_iam_policy.reports_reader.arn
}
