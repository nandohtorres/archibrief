output "frontend_url" {
  description = "CloudFront URL for the site. Always served, alongside any custom domain."
  value       = "https://${module.frontend_hosting.cloudfront_domain_name}"
}

output "api_endpoint" {
  value = module.api_gateway.api_endpoint
}

output "admin_key_secret_arn" {
  description = "Retrieve the pre-shared admin credential from Secrets Manager using this ARN, not from Terraform state/output directly."
  value       = module.api_gateway.admin_key_secret_arn
}

# Custom-domain outputs. The DNS records themselves are not managed by
# Terraform: Cloudflare is the DNS host, not Route53 (see this
# environment's README for the two-phase apply).

output "acm_validation_records" {
  description = "Add each of these as a CNAME in Cloudflare (DNS Only / grey cloud - proxying a validation record breaks it) before the second apply. Needed once, stays in place afterward."
  value = {
    for dvo in aws_acm_certificate.site.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
}

output "frontend_dns_target" {
  description = "CNAME target for archibrief.dev and www.archibrief.dev (apex CNAME through Cloudflare's CNAME flattening)."
  value       = module.frontend_hosting.cloudfront_domain_name
}

output "api_dns_target" {
  description = "CNAME target for api.archibrief.dev. null until certificate_arn is set on the api_gateway module (after the cert is validated and the second apply has run)."
  value       = module.api_gateway.regional_domain_target
}
