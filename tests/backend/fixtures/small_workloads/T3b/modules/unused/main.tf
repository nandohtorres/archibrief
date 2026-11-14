
resource "aws_security_group" "old_admin" {
  name = "abandoned-sample"
  vpc_id = "vpc-0123456789abcdef0"
  ingress {
   from_port = 22
   to_port = 22
   protocol = "tcp"
   cidr_blocks = ["0.0.0.0/0"]
  }
}
