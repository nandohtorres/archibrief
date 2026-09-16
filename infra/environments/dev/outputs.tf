output "frontend_url" {
  description = "Live CloudFront URL — the actual site to visit until Phase B's custom domain lands."
  value       = "https://${module.frontend_hosting.cloudfront_domain_name}"
}

output "api_endpoint" {
  value = module.api_gateway.api_endpoint
}

output "admin_key_secret_arn" {
  description = "Retrieve the real pre-shared admin credential value from Secrets Manager using this ARN, not from Terraform state/output directly."
  value       = module.api_gateway.admin_key_secret_arn
}
