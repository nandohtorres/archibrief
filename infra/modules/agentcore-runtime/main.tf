# Terraform module: agentcore-runtime
# Deploys the AgentCore Runtime that hosts the PreflightGate -> Retrieve ->
# Reason LangGraph subworkflow (ADR-0028); backend/agent/runtime_entrypoint.py
# is the code it runs. Its agent_runtime_arn feeds the InvokeAgent task in
# modules/step-functions-lambda.
#
# Deployed as a ZIP (agent_runtime_artifact.code_configuration) rather than
# a container: the provider supports it, LangGraph, boto3 and pydantic don't
# need a container, and it keeps every piece of infrastructure in
# Terraform. Container deployment (ECR + Docker) is the fallback if that
# ever stops holding.
#
# The ZIP must be built for Linux ARM64 (native wheels such as pydantic's
# compiled core fail if built on another platform), stay under the 250 MB
# package limit, and include the JSON data files backend/corpus/
# lexical_index.py reads at import time. backend/agent/build_runtime_package.py
# builds it.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# The runtime's deployment artifact gets its own bucket, separate from the
# review-data bucket in modules/s3 (ADR-0007/ADR-0042).
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

# var.agent_runtime_zip_path must exist on disk before plan; it is built by
# backend/agent/build_runtime_package.py.
resource "aws_s3_object" "runtime_code" {
  bucket = aws_s3_bucket.artifact.id
  key    = "runtime/agentcore-runtime.zip"
  source = var.agent_runtime_zip_path
  # source_hash rather than etag: with SSE-KMS the object's ETag is not an
  # MD5 of the content, so etag-based change detection is unreliable.
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
    # Confused-deputy protection: only AgentCore runtimes in this account
    # may assume the role.
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

# bedrock:InvokeModel also covers the Converse API; there is no separate
# Converse action. GetInferenceProfile is needed for the cross-region
# inference profile ARNs. The model list matches modules/iam's runtime
# boundary and deploy-role-policy.example.json; keep them in sync.
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
      # Titan V2 embeddings (ADR-0035) for the retrieve step's query
      # embedding; invoked by foundation-model ARN, no inference profile.
      "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0",
    ]
  }

  # query_vectors asks for metadata (returnMetadata=True), which needs
  # GetVectors alongside QueryVectors.
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

  # Not scoped to a log group ARN: the runtime's log group name embeds the
  # AWS-generated runtime ID, which doesn't exist until the runtime is
  # created, and the runtime needs this role first. Scoping it would be a
  # circular dependency. DescribeLogGroups has no resource-level scoping.
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

# entry_point must be a list, and code.s3.prefix names the exact ZIP object
# key, not a folder.
resource "aws_bedrockagentcore_agent_runtime" "review" {
  agent_runtime_name = replace(var.name_prefix, "-", "_")
  role_arn           = aws_iam_role.agentcore_execution.arn

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

  # Set explicitly rather than relying on runtime_entrypoint.py's fallback
  # defaults, which exist only so the module imports in tests. An empty
  # guardrail ID, for example, fails later with a confusing error.
  environment_variables = {
    ARCHIBRIEF_GUARDRAIL_ID         = var.guardrail_id
    ARCHIBRIEF_GUARDRAIL_VERSION    = var.guardrail_version
    ARCHIBRIEF_VECTOR_BUCKET        = var.vector_bucket_name
    ARCHIBRIEF_VECTOR_INDEX         = var.vector_index_name
    ARCHIBRIEF_REASONING_MODEL_ID   = var.reasoning_model_id
    ARCHIBRIEF_REASONING_MAX_TOKENS = tostring(var.reasoning_max_tokens)
    AWS_REGION                      = data.aws_region.current.name
    # AgentCore caches the ZIP it read at creation and does not re-read the
    # S3 key when its content changes, so a new upload alone runs stale
    # code. Tying an env var to the ZIP's hash makes Terraform update this
    # resource whenever the code changes, which makes AgentCore refetch it.
    ARCHIBRIEF_CODE_VERSION = aws_s3_object.runtime_code.source_hash
  }

  # The runtime only calls public AWS endpoints (Bedrock, S3 Vectors), so
  # it needs no VPC.
  network_configuration {
    network_mode = "PUBLIC"
  }

  tags = var.tags
}
