# Trap: admin wildcard attached inline on the role, not as aws_iam_policy.
resource "aws_iam_role" "worker" {
  name               = "worker"
  assume_role_policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}
POLICY
}

resource "aws_iam_role_policy" "worker_inline" {
  role   = aws_iam_role.worker.id
  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]
}
POLICY
}
