variable "vpc_id" {
  type = string
}

# Same resource name as the root module's and the sibling module's "db".
resource "aws_security_group" "db" {
  name   = "db"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}
