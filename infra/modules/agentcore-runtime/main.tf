# Terraform module: agentcore-runtime
# Deploys the AgentCore Runtime hosting the PreflightGate -> Retrieve ->
# Reason LangGraph subworkflow (ADR-0028) — backend/agent/runtime_entrypoint.py
# is the code this module runs. Once this module's agent_runtime_arn is
# wired into modules/step-functions-lambda's agentcore_runtime_arn input,
# the InvokeAgent task in that module's state machine stops pointing at
# its "not-yet-deployed" placeholder ARN.
#
# ZIP-based deployment (aws_bedrockagentcore_agent_runtime's
# agent_runtime_artifact.code_configuration), not container/ECR — confirmed
# 2026-09-16 directly against the locked hashicorp/aws 6.63.0 provider
# docs that this is a real, supported path (not a workaround inferred from
# AWS's newer CDK-based `agentcore` CLI, which this project deliberately
# does not use — every other piece of infra here is Terraform, keep it
# that way). LangGraph + boto3 + pydantic don't themselves require a
# container. Genuinely unverified: no live example was found of this exact
# combination (LangGraph + ZIP/code_configuration + native Terraform
# aws_bedrockagentcore_agent_runtime) — prior art exists for LangGraph-on-
# AgentCore via container deployment, and for ZIP/code deployment via
# Terraform for non-LangGraph agents, but not this combination. If this
# doesn't validate/apply cleanly, container deployment (ECR + Docker) is
# the documented fallback, not a hypothetical.
#
# Packaging is a real, currently-unmet prerequisite (same TODO(account-setup)
# deferral pattern as modules/step-functions-lambda's lambda_zip_paths):
# the ZIP must be built for Linux ARM64 (this project is developed on
# Windows — a Windows-built ZIP containing native wheels, e.g. pydantic's
# compiled core, can fail at deployment/import on ARM64 Linux), stay under
# the 250 MB package limit, and include backend/corpus/'s JSON data files
# that backend/corpus/lexical_index.py reads from disk at import time.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Dedicated bucket for the runtime's own deployment artifact — separate
# from modules/s3's "source of truth" bucket (ADR-0007/ADR-0042), which is
# for review data, not deployment packages.
resource "aws_s3_bucket" "artifact" {
  bucket = "${var.name_prefix}-agentcore-artifact"
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "artifact" {
  bucket                  = aws_s3_bucket.artifact.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifact" {
  bucket = aws_s3_bucket.artifact.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# TODO(account-setup): same deferral as modules/step-functions-lambda's
# lambda_zip_paths — var.agent_runtime_zip_path won't exist on disk until
# a real CI packaging step runs (backend/agent/runtime_entrypoint.py +
# backend + backend/corpus's JSON data files, zipped for Linux ARM64).
# This resource genuinely cannot plan/apply cleanly until that exists —
# not a code bug, an account/CI bootstrap gap, consistent with how every
# other placeholder in this environment is documented.
resource "aws_s3_object" "runtime_code" {
  bucket = aws_s3_bucket.artifact.id
  key    = "runtime/agentcore-runtime.zip"
  source = var.agent_runtime_zip_path
  etag   = filemd5(var.agent_runtime_zip_path)
}

data "aws_iam_policy_document" "agentcore_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    # Confused-deputy protection for a service principal — the same
    # pattern AWS documents for other service-assumed roles in this
    # account. Scopes which specific AgentCore runtime is allowed to
    # assume this role, not just which account.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:runtime/*"]
    }
  }
}

resource "aws_iam_role" "agentcore_execution" {
  name                 = "${var.name_prefix}-agentcore-runtime"
  assume_role_policy   = data.aws_iam_policy_document.agentcore_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

# bedrock:InvokeModel covers the Converse API too — confirmed 2026-09-16
# against AWS's own IAM docs ("other actions, such as Converse... are
# blocked automatically when InvokeModel is denied"); there is no separate
# bedrock:Converse allow-action. GetInferenceProfile is separately needed
# for the cross-region inference profile ARNs this project uses. Same dual
# Sonnet-5/Sonnet-4.6 ARN pattern as deploy-role-policy.example.json's
# BedrockReasoningInvoke statement and modules/iam's runtime boundary fix
# (2026-09-16) — kept in sync deliberately, not accidentally duplicated.
data "aws_iam_policy_document" "agentcore_execution" {
  statement {
    sid       = "ApplyGuardrail"
    effect    = "Allow"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = ["arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:guardrail/${var.guardrail_id}"]
  }

  statement {
    sid    = "ReasoningInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:GetInferenceProfile",
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-5",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-5",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-4-6",
    ]
  }

  # S3VectorsClient.query_vectors (backend/shared/clients/__init__.py)
  # requests returnMetadata=True, which needs GetVectors alongside
  # QueryVectors — confirmed by reading that client method directly, not
  # assumed from the API name alone.
  statement {
    sid       = "VectorsQuery"
    effect    = "Allow"
    actions   = ["s3vectors:QueryVectors", "s3vectors:GetVectors"]
    resources = ["arn:aws:s3vectors:*:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket_name}/index/${var.vector_index_name}"]
  }

  statement {
    sid       = "ReadOwnArtifact"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifact.arn}/*"]
  }

  # Log-delivery/resource-policy actions don't support resource-level
  # scoping in IAM — same caveat as modules/iam's AllowLogging statement
  # and modules/step-functions-lambda's state_machine_invoke document.
  statement {
    sid    = "Logging"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "agentcore_execution" {
  name   = "${var.name_prefix}-agentcore-runtime-execution"
  role   = aws_iam_role.agentcore_execution.id
  policy = data.aws_iam_policy_document.agentcore_execution.json
}

# UNVERIFIED field names/enum values, flagged rather than guessed with
# false confidence (2026-09-16): the exact `runtime` enum value AgentCore
# expects for a Python 3.12 ZIP artifact, and network_configuration's
# exact required shape, were not confirmed against the live Terraform
# provider schema (only the top-level required-argument list and
# code_configuration's general shape were independently confirmed). A
# `terraform validate` run (Fernando's, not run here per this task's
# constraints) against this exact block is the fast, cheap way to catch a
# wrong enum/attribute name — much cheaper than guessing further without
# being able to check.
resource "aws_bedrockagentcore_agent_runtime" "review" {
  agent_runtime_name = replace(var.name_prefix, "-", "_")
  role_arn            = aws_iam_role.agentcore_execution.arn

  agent_runtime_artifact {
    code_configuration {
      entry_point = "backend/agent/runtime_entrypoint.py"
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket = aws_s3_bucket.artifact.id
          prefix = "runtime/"
        }
      }
    }
  }

  # No VPC requirement identified for this workload (it only calls
  # Bedrock/S3 Vectors public AWS API endpoints, no private resources) —
  # PUBLIC is the documented default/simple path; AgentCore VPC is a
  # separate, optional add-on capability this module deliberately doesn't
  # use. Exact required sub-shape of network_configuration for PUBLIC mode
  # is part of the same unverified-schema caveat above.
  network_configuration {
    network_mode = "PUBLIC"
  }

  tags = var.tags
}
