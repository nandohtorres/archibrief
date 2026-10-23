# A cross-account trust guarded by sts:ExternalId, written two ways.
resource "aws_iam_role" "partner_json" {
  name = "partner-json"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::111122223333:root" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "sts:ExternalId" = "partner-7f3a" } }
    }]
  })
}

data "aws_iam_policy_document" "partner_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::111122223333:root"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = ["partner-7f3a"]
    }
  }
}

resource "aws_iam_role" "partner_doc" {
  name               = "partner-doc"
  assume_role_policy = data.aws_iam_policy_document.partner_trust.json
}
