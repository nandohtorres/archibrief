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

# Phase B (2026-10-14) custom-domain outputs. None of these are managed
# by Terraform directly - Cloudflare is the DNS host, not Route53 (see
# this environment's README for the full two-phase apply sequence).

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
  description = "CNAME target for archibrief.dev and www.archibrief.dev (apex CNAME via Cloudflare's CNAME flattening - Cloudflare supports this at the root, most registrars don't)."
  value       = module.frontend_hosting.cloudfront_domain_name
}

output "api_dns_target" {
  description = "CNAME target for api.archibrief.dev. null until certificate_arn is actually set on the api_gateway module (i.e. until the cert is validated and this file's second apply has run)."
  value       = module.api_gateway.regional_domain_target
}
