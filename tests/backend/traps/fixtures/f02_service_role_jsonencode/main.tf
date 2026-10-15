# Red herring: a normal Lambda execution role, trust policy via jsonencode.
resource "aws_iam_role" "lambda_exec" {
  name = "lambda-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
