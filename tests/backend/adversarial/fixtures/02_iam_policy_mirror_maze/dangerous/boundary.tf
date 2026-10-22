# AdministratorAccess on an EC2 role, capped by a permissions boundary that
# only allows reading one bucket. Effective permissions are the
# intersection of the identity policy and the boundary.
resource "aws_iam_policy" "read_only_boundary" {
  name = "read-only-boundary"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "s3:GetObject", Resource = "arn:aws:s3:::maze-reports/*" }]
  })
}

resource "aws_iam_role" "bounded_worker" {
  name                 = "bounded-worker"
  permissions_boundary = aws_iam_policy.read_only_boundary.arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bounded_worker_admin" {
  role       = aws_iam_role.bounded_worker.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
