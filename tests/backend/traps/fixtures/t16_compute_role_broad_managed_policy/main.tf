# Trap: broad AWS-managed policies on roles that running code can use,
# attached the two other ways (separate attachment resources), one with
# the partition interpolated into the ARN.
data "aws_partition" "current" {}

resource "aws_iam_role" "task_role" {
  name = "orders-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = ["ecs-tasks.amazonaws.com"] }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_admin" {
  role       = aws_iam_role.task_role.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_role" "report_fn" {
  name = "report-fn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy_attachment" "report_dynamo" {
  name       = "report-dynamo"
  roles      = [aws_iam_role.report_fn.name]
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}
