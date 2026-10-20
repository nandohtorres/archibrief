# Triggers the rule-engine rules no demo or trap fixture does, so every
# rule title is checked against the catalog's title matching.
resource "aws_api_gateway_stage" "prod" {
  stage_name = "prod"
}

resource "aws_cloudtrail" "main" {
  name = "main"
}

resource "aws_dynamodb_table" "orders" {
  name     = "orders"
  hash_key = "id"
}

resource "aws_ebs_volume" "data" {
  availability_zone = "us-east-1a"
  size              = 20
}

resource "aws_iam_role" "partner" {
  name = "partner"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::111122223333:root" }
    }]
  })
}

resource "aws_lambda_function" "worker" {
  function_name = "worker"
  role          = "arn:aws:iam::111122223333:role/worker"
  handler       = "app.handler"
  runtime       = "python3.12"
  environment {
    variables = {
      API_KEY = "placeholder"
    }
  }
}

resource "aws_db_instance" "main" {
  engine         = "mysql"
  instance_class = "db.t3.micro"
}

resource "aws_subnet" "public" {
  vpc_id                  = "vpc-123"
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
}
