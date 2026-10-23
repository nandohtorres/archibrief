# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# A backup plan protects only what a backup selection assigns to it. All of
# a plan's rules apply. copy_action names a destination vault ARN; another
# vault is not another Region or account unless that vault is.
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

resource "aws_db_instance" "prod_ledger" {
  identifier                  = "prod-ledger"
  engine                      = "postgres"
  instance_class              = "db.t3.medium"
  allocated_storage           = 50
  username                    = "ledger"
  manage_master_user_password = true
  storage_encrypted           = true
  multi_az                    = true
  backup_retention_period     = 7
  deletion_protection         = true
  tags = {
    env = "prod"
  }
}

resource "aws_db_instance" "dev_sandbox" {
  identifier                  = "dev-sandbox"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "sandbox"
  manage_master_user_password = true
  storage_encrypted           = true
  backup_retention_period     = 7
  tags = {
    env = "dev"
  }
}

resource "aws_backup_vault" "primary" {
  name = "primary"
}

# Same provider, so the same Region and account as "primary".
resource "aws_backup_vault" "secondary" {
  name = "secondary"
}

resource "aws_backup_plan" "nightly" {
  name = "nightly"

  rule {
    rule_name         = "rule_01"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 1 * * ? *)"

    lifecycle {
      delete_after = 35
    }
  }

  rule {
    rule_name         = "rule_02"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 2 * * ? *)"

    lifecycle {
      delete_after = 35
    }
  }

  rule {
    rule_name         = "rule_03"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 3 * * ? *)"

    lifecycle {
      delete_after = 35
    }
  }

  rule {
    rule_name         = "rule_04"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 4 * * ? *)"

    lifecycle {
      delete_after = 35
    }

    copy_action {
      destination_vault_arn = aws_backup_vault.secondary.arn
    }
  }
}

resource "aws_backup_selection" "prod_and_dev" {
  name         = "prod_and_dev"
  plan_id      = aws_backup_plan.nightly.id
  iam_role_arn = "arn:aws:iam::123456789012:role/backup"
  resources    = [aws_db_instance.prod_ledger.arn, aws_db_instance.dev_sandbox.arn]
}
