# Trap: full admin policy written with jsonencode() instead of a heredoc.
resource "aws_iam_policy" "app_runtime" {
  name = "app-runtime"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "*"
      Resource = "*"
    }]
  })
}
