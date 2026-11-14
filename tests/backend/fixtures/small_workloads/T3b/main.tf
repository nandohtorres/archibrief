terraform {
  required_version = ">= 1.5.0"
  required_providers {
    random = { source = "hashicorp/random", version = ">= 3.6, < 4.0" }
    aws = { source = "hashicorp/aws", version = ">= 6.0, < 7.0" }
  }
}
provider "aws" { region = "us-east-2" }

resource "random_id" "exchange" {
  byte_length = 4
}

resource "terraform_data" "deployment_marker" {
  input = "partner-exchange-v1"
}

resource "aws_security_group" "legacy_console" {
  count = 0
  name = "retired-console"
  vpc_id = "vpc-0123456789abcdef0"
  ingress {
   from_port = 22
   to_port = 22
   protocol = "tcp"
   cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "partner" {
  name = "p1-partner"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::111122223333:root"
        },
        "Action": "sts:AssumeRole",
        "Condition": {
          "StringEquals": {
            "sts:ExternalId": "p1-partner-exchange"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "partner" {
  name = "partner-exchange-access"
  role = aws_iam_role.partner.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "ReadSetting1",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-1"
      },
      {
        "Sid": "ReadSetting2",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-2"
      },
      {
        "Sid": "ReadSetting3",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-3"
      },
      {
        "Sid": "ReadSetting4",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-4"
      },
      {
        "Sid": "ReadSetting5",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-5"
      },
      {
        "Sid": "ReadSetting6",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-6"
      },
      {
        "Sid": "ReadSetting7",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-7"
      },
      {
        "Sid": "ReadSetting8",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-8"
      },
      {
        "Sid": "ReadSetting9",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-9"
      },
      {
        "Sid": "ReadSetting10",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-10"
      },
      {
        "Sid": "ReadSetting11",
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-2:123456789012:parameter/partner/routing/setting-11"
      },
      {
        "Sid": "LegacyObjectAccess",
        "Effect": "Allow",
        "Action": "s3:*",
        "Resource": "*"
      }
    ]
  })
}

resource "aws_ebs_encryption_by_default" "regional" {
  enabled = true
}

resource "aws_s3_bucket" "exchange_archive" {
  bucket = "archibrief-p1-t3b-exchange-archive-example"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "exchange_archive" {
  bucket = aws_s3_bucket.exchange_archive.id
  block_public_acls = true
  ignore_public_acls = true
  block_public_policy = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "exchange_archive" {
  bucket = aws_s3_bucket.exchange_archive.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "exchange_archive" {
  bucket = aws_s3_bucket.exchange_archive.id
  depends_on = [aws_s3_bucket_versioning.exchange_archive]
  rule {
   id = "scheduled-expiration"
   status = "Enabled"
   filter { prefix = "" }
   expiration { days = 90 }
   noncurrent_version_expiration { noncurrent_days = 90 }
   abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_policy" "exchange_archive" {
  bucket = aws_s3_bucket.exchange_archive.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPlaintextTransport",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "${aws_s3_bucket.exchange_archive.arn}",
          "${aws_s3_bucket.exchange_archive.arn}/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      }
    ]
  })
}

resource "aws_kms_key" "archive" {
  description = "Customer archive encryption"
  enable_key_rotation = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "archive" {
  name = "alias/p1-archive"
  target_key_id = aws_kms_key.archive.key_id
}

resource "aws_cloudwatch_log_group" "exchange_audit" {
  name = "/p1/T3b/exchange_audit"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "partner_access" {
  name = "/p1/T3b/partner_access"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "reconciliation" {
  name = "/p1/T3b/reconciliation"
  retention_in_days = 90
}

resource "aws_sns_topic" "operations" {
  name = "p1-exchange-operations"
  kms_master_key_id = aws_kms_alias.archive.name
}

resource "aws_iam_policy" "reader_boundary" {
  name = "p1-reader-boundary"
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "s3:GetObject",
        "Resource": "${aws_s3_bucket.exchange_archive.arn}/published/*"
      }
    ]
  })
}

resource "aws_iam_role" "archive_reader" {
  name = "p1-archive-reader"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::111122223333:root"
        },
        "Action": "sts:AssumeRole",
        "Condition": {
          "StringEquals": {
            "sts:ExternalId": "p1-partner-exchange"
          }
        }
      }
    ]
  })
  permissions_boundary = aws_iam_policy.reader_boundary.arn
}

resource "aws_iam_role_policy" "archive_reader" {
  name = "legacy-reader-grants"
  role = aws_iam_role.archive_reader.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "*",
        "Resource": "*"
      }
    ]
  })
}

module "intake" {
  source = "./modules/lane"
  lane = "intake"
  pitr_enabled = false
  failed_retention = 1209600
}
module "fulfillment" {
  source = "./modules/lane"
  lane = "fulfillment"
  pitr_enabled = true
  failed_retention = 60
}
module "archive_bridge" {
  source = "terraform-aws-modules/s3-bucket/aws"
  version = ">= 5.0, < 6.0"
  bucket = "p1-external-archive-bridge-example"
}
module "disabled_bridge" {
  count = 0
  source = "terraform-aws-modules/s3-bucket/aws"
  version = ">= 5.0, < 6.0"
}
