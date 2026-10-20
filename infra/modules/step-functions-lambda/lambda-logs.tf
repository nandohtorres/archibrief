# Lambda creates /aws/lambda/<name> on a function's first run, with no
# expiry. Owning each group here sets its retention.
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = merge(
    { for key, fn in aws_lambda_function.this : key => fn.function_name },
    { mark_review_failed = aws_lambda_function.mark_review_failed.function_name },
  )
  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.lambda_log_retention_days
  tags              = var.tags
}
