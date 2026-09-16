variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "cognito_user_pool_id" {
  type = string
}

variable "cognito_user_pool_client_id" {
  type = string
}

variable "state_machine_arn" {
  type = string
}

variable "domain_name" {
  type    = string
  default = "api.archibrief.dev"
}

variable "throttling_burst_limit" {
  type    = number
  default = 20
}

variable "throttling_rate_limit" {
  type    = number
  default = 10
}

variable "tags" {
  type    = map(string)
  default = {}
}
