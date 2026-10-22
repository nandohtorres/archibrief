variable "open_admin" {
  type    = bool
  default = false
}

resource "aws_security_group" "admin" {
  name = "edge-admin"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.open_admin ? "0.0.0.0/0" : "10.0.0.0/8"]
  }
}
