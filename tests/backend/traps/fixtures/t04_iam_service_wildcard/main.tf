# Trap: not literally "*", but every S3 action on every resource.
resource "aws_iam_policy" "reports_reader" {
  name   = "reports-reader"
  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]
}
POLICY
}
