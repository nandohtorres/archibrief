# Pinned per ADR-0004/ADR-0042. aws provider >= 6.24 required for the
# aws_s3vectors_* resources (ADR-0007) — verified against the Terraform
# Registry during this implementation pass, 2026-09-08.
# .terraform.lock.hcl gets committed once `terraform init` is actually run
# (requires AWS account bootstrap first — see Work-Project-Deployment-Roadmap.md).

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
