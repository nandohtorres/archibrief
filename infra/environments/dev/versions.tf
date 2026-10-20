# Pinned per ADR-0004/ADR-0042. aws provider >= 6.24 is required for the
# aws_s3vectors_* resources (ADR-0007). .terraform.lock.hcl is committed.

terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.24"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    bucket         = "archibrief-tfstate"
    key            = "dev/terraform.tfstate"
    region         = "us-east-2"
    dynamodb_table = "archibrief-tfstate-lock"
    encrypt        = true
  }
}
