output "public_api_url" {
  description = "The REST API's public stage URL. The frontend calls api.archibrief.dev, which maps to it."
  value       = var.public_edge_enabled ? aws_api_gateway_stage.public[0].invoke_url : null
}

output "regional_domain_target" {
  description = "The CNAME target for var.domain_name once certificate_arn is set (API Gateway's own regional domain, e.g. d-xxxx.execute-api.us-east-1.amazonaws.com) — null until then. Point api.archibrief.dev's DNS CNAME at this value."
  value       = var.certificate_arn == null ? null : aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
}
