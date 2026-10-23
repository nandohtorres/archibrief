# Source preparation only. Leave both switches false until an authorized plan,
# deployment, bypass tests and paid evaluation have been reviewed.
variable "public_edge_enabled" {
  type    = bool
  default = false
}

variable "public_access_enabled" {
  type    = bool
  default = false
}

variable "turnstile_secret_parameter_arn" {
  type    = string
  default = null
}

variable "turnstile_secret_parameter_name" {
  type    = string
  default = ""
}

output "public_api_url" {
  value = module.api_gateway.public_api_url
}

variable "verified_public_api_id" {
  type    = string
  default = ""
}
