output "parameter_name" {
  value = aws_ssm_parameter.kill_switch.name
}

output "parameter_arn" {
  value = aws_ssm_parameter.kill_switch.arn
}
