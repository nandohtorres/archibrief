output "api_endpoint" {
  value = aws_apigatewayv2_api.main.api_endpoint
}

output "api_id" {
  value = aws_apigatewayv2_api.main.id
}

output "admin_key_secret_arn" {
  description = "Secrets Manager ARN for the pre-shared admin credential (ADR-0044) — retrieve the value from here, never from Terraform state/output directly in normal use."
  value       = aws_secretsmanager_secret.admin_key.arn
}
