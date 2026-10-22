# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# Replica count says nothing about failure domains: instances in one AZ fail
# together. A provider alias named "dr" is only another Region if its region
# argument says so. A backup plan is not a recovery-time guarantee.
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

provider "aws" {
  alias  = "dr"
  region = "us-east-1"
}

resource "aws_rds_cluster" "core" {
  cluster_identifier          = "core"
  engine                      = "aurora-postgresql"
  master_username             = "core"
  manage_master_user_password = true
  storage_encrypted           = true
  backup_retention_period     = 7
  deletion_protection         = true
}

resource "aws_rds_cluster_instance" "core" {
  count              = 3
  identifier         = "core-${count.index}"
  cluster_identifier = aws_rds_cluster.core.id
  instance_class     = "db.r6g.large"
  engine             = aws_rds_cluster.core.engine
  availability_zone  = element(["us-east-1a", "us-east-1a", "us-east-1a"], count.index)
}

resource "aws_db_instance" "orders_primary" {
  identifier                  = "orders-primary"
  engine                      = "postgres"
  instance_class              = "db.t3.medium"
  allocated_storage           = 50
  username                    = "orders"
  manage_master_user_password = true
  storage_encrypted           = true
  multi_az                    = true
  backup_retention_period     = 7
}

resource "aws_db_instance" "orders_replica" {
  count               = 2
  identifier          = "orders-replica-${count.index}"
  replicate_source_db = aws_db_instance.orders_primary.identifier
  instance_class      = "db.t3.medium"
  storage_encrypted   = true
  availability_zone   = element(["us-east-1a", "us-east-1a"], count.index)
}

# The "dr" provider is in the same Region as the primary.
resource "aws_db_instance" "orders_dr" {
  provider            = aws.dr
  identifier          = "orders-dr"
  replicate_source_db = aws_db_instance.orders_primary.arn
  instance_class      = "db.t3.medium"
  storage_encrypted   = true
}

resource "aws_backup_vault" "main" {
  name = "main"
}

resource "aws_backup_plan" "daily" {
  name = "daily"

  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 5 * * ? *)"

    lifecycle {
      delete_after = 14
    }
  }
}
