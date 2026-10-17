variable "bucket_name" {
  type        = string
  description = "Name of the private S3 bucket holding the static export (frontend/out). Served only via CloudFront/OAC, never directly."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for the CloudFront OAC name and other non-bucket resource names, e.g. archibrief-dev."
}

# PriceClass_100 (US/Canada/Europe edge locations only) is the cheapest
# tier, enough for a low-traffic deployment without a global audience.
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
  description = "CSP connect-src value for the API Gateway origin, e.g. https://*.execute-api.us-east-1.amazonaws.com. A wildcard subdomain pattern, not the literal api_endpoint output, which would create a circular module dependency with api_gateway (it depends on this module's cloudfront_domain_name for CORS)."
}

# Custom domain support. Both default to values that keep the
# distribution on its default *.cloudfront.net certificate and domain, so
# the module works without a domain.
variable "aliases" {
  type        = list(string)
  default     = []
  description = "Alternate domain names (CNAMEs) for the distribution, e.g. [\"archibrief.dev\", \"www.archibrief.dev\"]. Requires certificate_arn to be set to a validated ACM cert in us-east-1 covering every name here."
}

variable "certificate_arn" {
  type        = string
  default     = null
  description = "ACM certificate ARN (must be in us-east-1, a CloudFront requirement independent of price_class) covering every name in `aliases`. Leave null to keep using CloudFront's default certificate."
}
