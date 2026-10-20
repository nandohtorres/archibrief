variable "bucket_name" {
  type        = string
  description = "Name of the private S3 bucket holding the static export (frontend/out). Served only via CloudFront/OAC, never directly."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for the CloudFront OAC name and other non-bucket resource names, e.g. archibrief-dev."
}

# PriceClass_100 (US/Canada/Europe edge locations only) is the cheapest
# tier — fine for a solo portfolio demo with no global audience. Widen
# this if that ever stops being true.
variable "price_class" {
  type    = string
  default = "PriceClass_100"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "api_origin_pattern" {
  type        = string
  description = "CSP connect-src value for the API Gateway origin, e.g. https://*.execute-api.us-east-1.amazonaws.com. A wildcard subdomain pattern, not the literal api_endpoint output — using the literal would create a circular module dependency with api_gateway (which already depends on this module's cloudfront_domain_name for CORS)."
}

# Phase B (2026-10-14): custom domain support. Both default to values
# that keep the distribution on its default *.cloudfront.net cert/domain
# (the pre-existing behavior) when unset, so this module stays usable
# without a domain for any environment that doesn't want one yet.
variable "aliases" {
  type        = list(string)
  default     = []
  description = "Alternate domain names (CNAMEs) for the distribution, e.g. [\"archibrief.dev\", \"www.archibrief.dev\"]. Requires certificate_arn to be set to a validated ACM cert in us-east-1 covering every name here."
}

variable "certificate_arn" {
  type        = string
  default     = null
  description = "ACM certificate ARN (us-east-1 — CloudFront's own hard requirement, independent of the distribution's price_class/edge locations) covering every name in `aliases`. Leave null to keep using CloudFront's default certificate."
}
