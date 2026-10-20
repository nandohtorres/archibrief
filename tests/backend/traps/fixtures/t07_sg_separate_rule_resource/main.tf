# Trap: the open SSH rule is a separate aws_security_group_rule resource.
resource "aws_security_group" "bastion" {
  name = "bastion"
}

resource "aws_security_group_rule" "ssh_from_anywhere" {
  type              = "ingress"
  security_group_id = aws_security_group.bastion.id
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
}
