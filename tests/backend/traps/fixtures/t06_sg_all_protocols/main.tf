# Trap: protocol -1 with ports 0-0 means ALL traffic, including 22/3389/5432.
resource "aws_security_group" "app" {
  name = "app"
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
