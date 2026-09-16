output "state_machine_arn" {
  value = aws_sfn_state_machine.review.arn
}

output "lambda_function_arns" {
  value = { for k, fn in aws_lambda_function.this : k => fn.arn }
}
