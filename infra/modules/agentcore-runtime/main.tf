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
  # source_hash, not etag/filemd5 — confirmed 2026-09-16 against
  # HashiCorp's own aws_s3_object docs: when the destination bucket uses
  # SSE-KMS (this one does, see aws_s3_bucket_server_side_encryption_configuration
  # above), the object's real S3 ETag is not a plain MD5 of the plaintext
  # content, so comparing etag/filemd5 for change detection is unreliable.
  # source_hash is computed client-side and doesn't depend on how S3
  # computed its own ETag.
  source_hash = filemd5(var.agent_runtime_zip_path)
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
      # Titan V2 embeddings (ADR-0035) — confirmed missing 2026-09-16 via
      # Codex review: retrieve_node's BedrockEmbeddingClient calls
      # invoke_model against amazon.titan-embed-text-v2:0 (backend/shared/
      # clients/__init__.py), and this runtime's own retrieve_node call
      # (via compiled_graph()) needs this permission just as much as the
      # reasoning call does. No inference profile needed for Titan — it's
      # invoked directly by foundation-model ARN.
      "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0",
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

# `PYTHON_3_12` and `network_mode = "PUBLIC"` confirmed correct against
# the locked hashicorp/aws 6.63.0 provider docs (Codex review 2026-09-16,
# cross-checked against this project's own independent research, not
# taken purely on trust). entry_point and code.s3.prefix below were fixed
# per that same review — entry_point must be a list (a single string was
# rejected by the schema), and the S3 code source needs prefix to name
# the exact ZIP object key (matching aws_s3_object.runtime_code.key
# above), not a folder-style prefix that assumes AgentCore infers a
# filename. Neither was independently re-derived beyond Codex's citation
# of the provider docs — a real `terraform validate` (Fernando's, not run
# here) is still the authoritative check.
resource "aws_bedrockagentcore_agent_runtime" "review" {
  agent_runtime_name = replace(var.name_prefix, "-", "_")
  role_arn            = aws_iam_role.agentcore_execution.arn

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["backend/agent/runtime_entrypoint.py"]
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket = aws_s3_bucket.artifact.id
          prefix = aws_s3_object.runtime_code.key
        }
      }
    }
  }

  # Explicit, not defaulted — a real deployment shouldn't depend on
  # runtime_entrypoint.py's own os.environ.get(..., fallback) defaults,
  # which exist only so the file stays importable/testable without a real
  # environment (same reasoning as every other explicit env-var wiring in
  # this project). ARCHIBRIEF_GUARDRAIL_ID defaulting to "" silently
  # broke guardrails.check() with a confusing KeyError in this exact
  # project already (see Work-Project-Issues-Log.md, 2026-09-16) — that
  # failure mode is exactly what wiring this in for real prevents.
  environment_variables = {
    ARCHIBRIEF_GUARDRAIL_ID          = var.guardrail_id
    ARCHIBRIEF_GUARDRAIL_VERSION     = var.guardrail_version
    ARCHIBRIEF_VECTOR_BUCKET         = var.vector_bucket_name
    ARCHIBRIEF_VECTOR_INDEX          = var.vector_index_name
    ARCHIBRIEF_REASONING_MODEL_ID    = var.reasoning_model_id
    ARCHIBRIEF_REASONING_MAX_TOKENS  = tostring(var.reasoning_max_tokens)
    AWS_REGION                       = data.aws_region.current.name
  }

  # No VPC requirement identified for this workload (it only calls
  # Bedrock/S3 Vectors public AWS API endpoints, no private resources) —
  # PUBLIC is the documented default/simple path; AgentCore VPC is a
  # separate, optional add-on capability this module deliberately doesn't
  # use.
  network_configuration {
    network_mode = "PUBLIC"
  }

  tags = var.tags
}
