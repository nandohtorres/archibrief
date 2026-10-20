# Red herring: a compute role with narrow AWS-managed policies, and a
# human admin role (not usable by running code) with AdministratorAccess.
resource "aws_iam_role" "app" {
  name = "app"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
  ]
}

resource "aws_iam_role" "breakglass" {
  name = "breakglass"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::111122223333:root" }
      Condition = { Bool = { "aws:MultiFactorAuthPresent" = "true" } }
    }]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}
