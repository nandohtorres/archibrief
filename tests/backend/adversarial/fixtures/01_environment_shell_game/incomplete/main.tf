terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# No default and no tfvars: the value is supplied at plan time.
variable "db_public" {
  type = bool
}

resource "aws_db_instance" "orders" {
  identifier                  = "orders"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "app"
  manage_master_user_password = true
  storage_encrypted           = true
  multi_az                    = true
  publicly_accessible         = var.db_public
}

module "network" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.8.1"
}
