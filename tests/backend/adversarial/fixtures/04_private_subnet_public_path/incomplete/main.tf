# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# A subnet is public when its route table sends 0.0.0.0/0 to an internet
# gateway, whatever it is called. A security group grants nothing until it
# is attached to an ENI; an attached group is necessary but not sufficient
# for reachability (routes, NACLs, public IPs and listeners also matter).
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# The allowed ranges come from a variable with no default.
variable "allowed_cidrs" {
  type = list(string)
}

resource "aws_security_group" "db_ingress" {
  name = "db-ingress"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }
}
