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

output "stage_arn" {
  description = "aws_apigatewayv2_stage ARN. Not a WAF attachment point: AWS WAF cannot be associated with an HTTP API (v2) stage, only REST API stages, so this API has no WAF; abuse limits are stage throttling + the admin authorizer."
  value       = aws_apigatewayv2_stage.default.arn
}

output "regional_domain_target" {
  description = "The CNAME target for var.domain_name once certificate_arn is set (API Gateway's own regional domain, e.g. d-xxxx.execute-api.us-east-1.amazonaws.com) — null until then. Point api.archibrief.dev's DNS CNAME at this value."
  value       = var.certificate_arn == null ? null : aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
}
