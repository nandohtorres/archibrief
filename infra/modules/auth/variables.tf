variable "user_pool_name" {
  type    = string
  default = "archibrief"
}

variable "domain" {
  type        = string
  description = "Public domain the frontend is served from, used for callback/logout URLs (e.g. archibrief.dev)."
  default     = "archibrief.dev"
}

variable "callback_urls" {
  type        = list(string)
  description = "OAuth callback URLs allowed for the app client."
  default     = ["https://archibrief.dev/auth/callback"]
}

variable "logout_urls" {
  type    = list(string)
  default = ["https://archibrief.dev/"]
}

variable "ses_source_arn" {
  type        = string
  description = "ARN of the SES-verified sending identity for the domain — TODO(account-setup): real value only exists once SES is set up during AWS account bootstrap."
}

variable "from_email_address" {
  type        = string
  description = "From-address for auth emails, e.g. no-reply@archibrief.dev."
  default     = "no-reply@archibrief.dev"
}

variable "tags" {
  type    = map(string)
  default = {}
}
