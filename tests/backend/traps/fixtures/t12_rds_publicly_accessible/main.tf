# Trap: encrypted and multi-AZ (looks hardened) but reachable from the internet.
resource "aws_db_instance" "orders" {
  identifier          = "orders"
  engine              = "postgres"
  instance_class      = "db.t4g.micro"
  allocated_storage   = 20
  storage_encrypted   = true
  multi_az            = true
  publicly_accessible = true
}
