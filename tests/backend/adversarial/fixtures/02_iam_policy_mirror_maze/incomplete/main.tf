terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# The policy text arrives at plan time; nothing here says what it grants.
variable "runtime_policy_json" {
  type = string
}

resource "aws_iam_policy" "runtime" {
  name   = "runtime"
  policy = var.runtime_policy_json
}
