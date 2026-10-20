# Red herring: IMDSv2 required, on the instance and on the launch template.
resource "aws_instance" "app" {
  ami           = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }
  root_block_device {
    encrypted = true
  }
}

resource "aws_launch_template" "app" {
  name_prefix   = "app-"
  image_id      = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  metadata_options {
    http_tokens = "required"
  }
}
