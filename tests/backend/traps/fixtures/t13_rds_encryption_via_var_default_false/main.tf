# Trap: encryption "configured" via a variable whose default is false.
variable "encrypt_storage" {
  type    = bool
  default = false
}

resource "aws_db_instance" "billing" {
  identifier        = "billing"
  engine            = "postgres"
  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  storage_encrypted = var.encrypt_storage
  multi_az          = true
}
