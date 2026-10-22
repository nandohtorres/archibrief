# Pinned semantics (not downloaded): Terraform >= 1.6, hashicorp/aws ~> 6.0.
# A subnet is public when its route table sends 0.0.0.0/0 to an internet
# gateway, whatever it is called. A security group grants nothing until it
# is attached to an ENI; an attached group is necessary but not sufficient
# for reachability (routes, NACLs, public IPs and listeners also matter).
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_vpc" "main" {
  cidr_block                       = "10.0.0.0/16"
  assign_generated_ipv6_cidr_block = true
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

# Named "private", but see the route table association below.
resource "aws_subnet" "private_db_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = false
}

resource "aws_subnet" "private_db_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = false
}

resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table_association" "db_a" {
  subnet_id      = aws_subnet.private_db_a.id
  route_table_id = aws_route_table.private_rt.id
}

resource "aws_db_subnet_group" "ledger" {
  name       = "ledger"
  subnet_ids = [aws_subnet.private_db_a.id, aws_subnet.private_db_b.id]
}

resource "aws_security_group" "app" {
  name   = "app"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Database access only from the app security group, never from a CIDR.
resource "aws_security_group" "db" {
  name   = "db"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_security_group" "bastion_v6" {
  name   = "bastion-v6"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    ipv6_cidr_blocks = ["2001:db8:1234::/48"]
  }
}

resource "aws_instance" "bastion" {
  ami                    = "ami-0123456789abcdef0"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.private_db_b.id
  vpc_security_group_ids = [aws_security_group.bastion_v6.id]

  metadata_options {
    http_tokens = "required"
  }
}

resource "aws_db_instance" "ledger" {
  identifier                  = "ledger"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "ledger"
  manage_master_user_password = true
  storage_encrypted           = true
  multi_az                    = true
  publicly_accessible         = false
  db_subnet_group_name        = aws_db_subnet_group.ledger.name
  vpc_security_group_ids      = [aws_security_group.db.id]
}

module "payments" {
  source = "./modules/a_payments"
  vpc_id = aws_vpc.main.id
}

module "reporting" {
  source = "./modules/b_reporting"
  vpc_id = aws_vpc.main.id
}
