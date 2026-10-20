# Lambda creates /aws/lambda/<name> on a function's first run, with no
# expiry. Owning each group here sets its retention. The groups already
# exist in deployed environments, so infra/environments/dev/log-groups.tf
# imports them instead of creating them. The chat functions own their log
# groups in chat.tf.
locals {
  api_lambda_log_functions = {
    admin_authorizer = aws_lambda_function.admin_authorizer.function_name
    get_review       = aws_lambda_function.get_review.function_name
    clarify_review   = aws_lambda_function.clarify_review.function_name
    deeper_review    = aws_lambda_function.deeper_review.function_name
    get_demo         = aws_lambda_function.get_demo.function_name
    create_upload    = aws_lambda_function.create_upload.function_name
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.api_lambda_log_functions
  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.lambda_log_retention_days
  tags              = var.tags
}
