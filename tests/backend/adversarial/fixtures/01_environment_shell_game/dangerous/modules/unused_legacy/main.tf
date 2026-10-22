# No module block calls this directory, so Terraform never creates these.
resource "aws_security_group" "legacy_ssh" {
  name = "legacy-ssh"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "legacy_db" {
  identifier          = "legacy"
  engine              = "mysql"
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  username            = "legacy"
  password            = "SYNTHETIC-NOT-A-SECRET-0101"
  publicly_accessible = true
}
