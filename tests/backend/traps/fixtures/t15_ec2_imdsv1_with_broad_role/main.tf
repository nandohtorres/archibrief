# Trap: the 2019 breach chain in miniature. A public reverse proxy on EC2
# with no metadata_options (IMDSv1 allowed unless the AMI or account says
# otherwise), whose instance role carries AmazonS3FullAccess. A request
# forgery on the proxy can read the role's credentials from the metadata
# service and then read every bucket in the account.
resource "aws_iam_role" "proxy_role" {
  name = "proxy-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
}

resource "aws_iam_instance_profile" "proxy" {
  name = "proxy-profile"
  role = aws_iam_role.proxy_role.name
}

resource "aws_instance" "proxy" {
  ami                         = "ami-0123456789abcdef0"
  instance_type               = "t3.micro"
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.proxy.name
}

resource "aws_launch_template" "workers" {
  name_prefix   = "workers-"
  image_id      = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  metadata_options {
    http_tokens = "optional"
  }
}
