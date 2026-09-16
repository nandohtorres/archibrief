# Terraform module: auth
# Cognito user pool: email/password primary sign-in + emailed one-time
# auth code as a second factor (ADR-0043) — not SMS, not TOTP, not a
# magic link. Passkeys/WebAuthn deferred past v1.
#
# Requires an SES-verified sending identity + the Essentials/Plus feature
# plan for native email MFA (verified via AWS docs, see
# Work-Project-Deployment-Roadmap.md). ses_caller_arn is a real value only
# once SES is set up during account bootstrap — until then it's a
# TODO(account-setup) placeholder in terraform.tfvars.example.

resource "aws_cognito_user_pool" "main" {
  name = var.user_pool_name

  username_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = "ON"

  email_mfa_configuration {
    message = "Your ArchiBrief verification code is {####}"
    subject = "ArchiBrief sign-in code"
  }

  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = var.ses_source_arn
    from_email_address    = var.from_email_address
  }

  auto_verified_attributes = ["email"]

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.user_pool_name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  allowed_oauth_flows                 = ["code"]
  allowed_oauth_scopes                = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = replace(var.domain, ".", "-")
  user_pool_id = aws_cognito_user_pool.main.id
}
