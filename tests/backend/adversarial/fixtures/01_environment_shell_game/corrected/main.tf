resource "aws_db_instance" "orders" {
  identifier                  = "orders"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "app"
  manage_master_user_password = true
  storage_encrypted           = true
  multi_az                    = true
  backup_retention_period     = 7
  deletion_protection         = true
  publicly_accessible         = var.db_public
}

# count resolves to 0 with the default (no tfvars sets enable_debug_sg).
resource "aws_security_group" "debug" {
  count = var.enable_debug_sg ? 1 : 0
  name  = "debug"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Never created: the module call has count = 0.
module "archive" {
  source = "./modules/archive"
  count  = 0
}

# The same local module, called twice with different inputs.
module "edge_prod" {
  source     = "./modules/edge"
  open_admin = false
}

module "edge_lab" {
  source     = "./modules/edge"
  open_admin = false
}
