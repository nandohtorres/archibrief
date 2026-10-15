# Trap: the newer standalone ingress-rule resource type (AWS provider v5+).
resource "aws_security_group" "db" {
  name = "db"
}

resource "aws_vpc_security_group_ingress_rule" "postgres_world" {
  security_group_id = aws_security_group.db.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
}
