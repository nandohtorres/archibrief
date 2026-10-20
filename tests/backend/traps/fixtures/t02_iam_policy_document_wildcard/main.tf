# Trap: the wildcard lives in a data source; the policy just references it.
data "aws_iam_policy_document" "everything" {
  statement {
    actions   = ["*"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "deploy" {
  name   = "deploy"
  policy = data.aws_iam_policy_document.everything.json
}
