# Trap: open to the whole IPv6 internet instead of 0.0.0.0/0.
resource "aws_security_group" "admin" {
  name = "admin"
  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    ipv6_cidr_blocks = ["::/0"]
  }
}
