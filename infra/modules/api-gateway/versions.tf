# Minimum versions for this module; infra/environments/dev/versions.tf pins
# the exact ones.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.24"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6"
    }
  }
}
