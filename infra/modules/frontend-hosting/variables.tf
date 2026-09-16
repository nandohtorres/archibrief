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
