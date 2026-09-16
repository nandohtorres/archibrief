# Terraform module: dynamodb
# Application profile/entitlements/job metadata/counters (ADR-0017,
# ADR-0034) — Cognito owns authentication identities, this module owns
# everything else. Every key pattern includes an ownership check at the
# application layer (ownerId in Reviews/GuestSessions); transient job
# records carry a TTL. Large payloads live in S3, not here — items are
# capped at 400 KB (ADR-0034), enforced in backend/lambdas/finalize.

resource "aws_dynamodb_table" "users" {
  name         = "${var.table_prefix}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "guest_sessions" {
  name         = "${var.table_prefix}-guest-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "sessionKey"

  attribute {
    name = "sessionKey"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "reviews" {
  name         = "${var.table_prefix}-reviews"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "reviewId"

  attribute {
    name = "reviewId"
    type = "S"
  }

  attribute {
    name = "ownerId"
    type = "S"
  }

  global_secondary_index {
    name            = "ownerId-index"
    hash_key        = "ownerId"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "findings" {
  name         = "${var.table_prefix}-findings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "reviewId"
  range_key    = "findingId"

  attribute {
    name = "reviewId"
    type = "S"
  }

  attribute {
    name = "findingId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "audit_log" {
  name         = "${var.table_prefix}-audit-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "auditId"

  attribute {
    name = "auditId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "usage_counters" {
  name         = "${var.table_prefix}-usage-counters"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "counterKey"

  attribute {
    name = "counterKey"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = var.tags
}
