# Terraform module: step-functions-lambda
# Step Functions (Standard) owns only the durable outer job lifecycle:
# accept, validate, persist input, invoke the agent stage once,
# validate/persist the result, publish status (ADR-0028). Each stateless
# Lambda (Ingest, RuleEngine, Validate, Audit, Finalize) gets its own
# least-privilege execution role, defined in this module next to the
# Lambda itself (ADR-0021), never a shared role. The reasoning/retrieval
# subworkflow runs in AgentCore Runtime; the state machine calls it once
# through an AWS SDK integration task (agentcore_runtime_arn).

locals {
  lambda_environment = {
    ingest = {
      GUARDRAIL_ID      = var.guardrail_id
      GUARDRAIL_VERSION = var.guardrail_version
    }
    audit = {
      # Table name is the last segment of arn:aws:dynamodb:<region>:<acct>:table/<name>.
      AUDIT_TABLE_NAME = element(split("/", var.audit_table_arn), 1)
    }
    # The Trivy layer mounts the binary at /opt/bin/trivy (ADR-0048).
    scan = {
      TRIVY_PATH    = "/opt/bin/trivy"
      TRIVY_VERSION = var.trivy_version
    }
  }

  # Every Lambda sets timeout and memory_size explicitly; the AWS defaults
  # (3 seconds, 128 MB) are too small. Lambda CPU scales with memory, and
  # at 128 MB HCL parsing with lark (an Earley parser) is CPU-starved
  # enough to time out on small inputs that parse in milliseconds locally.
  #
  # Ingest and RuleEngine get the most: Ingest downloads the archive,
  # calls Guardrails and parses HCL; RuleEngine also parses HCL (hcl_eval
  # resolves jsonencode() policies with hcl2.loads), and the first call in
  # a process builds lark's parser, which takes over a second. Validate is
  # pure in-memory compute; Audit, Finalize and StoreClarificationToken
  # each make one or two DynamoDB/S3 calls.
  lambda_specs = {
    ingest      = { handler = "backend.lambdas.ingest.handler.handler", zip = var.lambda_zip_paths.ingest, timeout = 30, memory_size = 1024 }
    rule_engine = { handler = "backend.lambdas.rule_engine.handler.handler", zip = var.lambda_zip_paths.rule_engine, timeout = 30, memory_size = 1024 }
    validate    = { handler = "backend.lambdas.validate.handler.handler", zip = var.lambda_zip_paths.validate, timeout = 10, memory_size = 256 }
    audit       = { handler = "backend.lambdas.audit.handler.handler", zip = var.lambda_zip_paths.audit, timeout = 10, memory_size = 256 }
    finalize    = { handler = "backend.lambdas.finalize.handler.handler", zip = var.lambda_zip_paths.finalize, timeout = 15, memory_size = 256 }
    # Invoked via the waitForTaskToken service integration pattern
    # (StoreClarificationToken state below) — its own return value is
    # discarded by Step Functions; only the later out-of-band
    # SendTaskSuccess (clarify_review Lambda, behind POST /reviews/{reviewId}/clarify)
    # actually completes this state. See backend/lambdas/
    # store_clarification_token/handler.py's module docstring.
    store_clarification_token = {
      handler     = "backend.lambdas.store_clarification_token.handler.handler"
      zip         = var.lambda_zip_paths.store_clarification_token
      timeout     = 10
      memory_size = 256
    }
    # Runs Trivy on the submitted Terraform (ADR-0048). Its own Lambda so
    # the third-party binary runs with read access to uploads/ and nothing
    # else. Trivy's own timeout is 60s; memory buys CPU for its HCL
    # evaluation.
    scan = {
      handler     = "backend.lambdas.scan.handler.handler"
      zip         = var.scan_zip_path
      timeout     = 90
      memory_size = 2048
    }
  }
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each             = local.lambda_specs
  name                 = "${var.name_prefix}-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  for_each   = local.lambda_specs
  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Validate is pure compute on its event payload. RuleEngine only reads
# the parsed Terraform Ingest stored under parsed/ (see below).
#
# Audit and Finalize each get only what their handler calls:
# - Audit: one PutItem on the audit table. Nothing else.
# - Finalize: GetItem (fetch-and-merge) + PutItem on the reviews table,
#   and PutObject only under reports/, where the evidence ledger lives
#   (backend/lambdas/finalize/handler.py). Not the audit table, and not
#   uploads/ or parsed/ in the same bucket.
data "aws_iam_policy_document" "audit_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [var.audit_table_arn]
  }
}

data "aws_iam_policy_document" "finalize_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [var.reviews_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/reports/*"]
  }
}

resource "aws_iam_role_policy" "audit_data_access" {
  name   = "${var.name_prefix}-audit-data-access"
  role   = aws_iam_role.lambda["audit"].id
  policy = data.aws_iam_policy_document.audit_data_access.json
}

resource "aws_iam_role_policy" "finalize_data_access" {
  name   = "${var.name_prefix}-finalize-data-access"
  role   = aws_iam_role.lambda["finalize"].id
  policy = data.aws_iam_policy_document.finalize_data_access.json
}

# These were previously one for_each policy with the same inline policy
# names. Move rather than destroy+create: with separate addresses
# Terraform could create the new policy and then delete the old one of
# the same name, leaving the role with none.
moved {
  from = aws_iam_role_policy.audit_finalize_data_access["audit"]
  to   = aws_iam_role_policy.audit_data_access
}

moved {
  from = aws_iam_role_policy.audit_finalize_data_access["finalize"]
  to   = aws_iam_role_policy.finalize_data_access
}

# store_clarification_token only ever reads/writes the one review item it
# was invoked for (GetItem to merge, PutItem to persist the pending
# token) — no audit-table or S3 access, unlike audit/finalize above.
data "aws_iam_policy_document" "store_clarification_token_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [var.reviews_table_arn]
  }
}

resource "aws_iam_role_policy" "store_clarification_token_data_access" {
  name   = "${var.name_prefix}-store-clarification-token-data-access"
  role   = aws_iam_role.lambda["store_clarification_token"].id
  policy = data.aws_iam_policy_document.store_clarification_token_data_access.json
}

# Ingest calls Guardrails inline (ADR-0033) using the GUARDRAIL_ID and
# GUARDRAIL_VERSION environment variables above. Always created, not
# conditioned on guardrail_id: on a fresh account the guardrail ID is
# unknown until apply, and Terraform can't plan a count from an unknown
# value.
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ingest_guardrails_apply" {
  statement {
    effect  = "Allow"
    actions = ["bedrock:ApplyGuardrail"]
    resources = [
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:guardrail/${var.guardrail_id}",
    ]
  }
}

resource "aws_iam_role_policy" "ingest_guardrails_apply" {
  name   = "${var.name_prefix}-ingest-guardrails-apply"
  role   = aws_iam_role.lambda["ingest"].id
  policy = data.aws_iam_policy_document.ingest_guardrails_apply.json
}

# Ingest downloads the client's uploaded archive from S3 (ADR-0045;
# _resolve_archive_path in backend/lambdas/ingest/handler.py). Scoped to
# the uploads/ prefix that create_upload's presigned POST writes into,
# never the whole reports bucket, which also holds Finalize's trusted
# evidence ledgers.
data "aws_iam_policy_document" "ingest_s3_download" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.reports_bucket_arn}/uploads/*"]
  }
  # Parsed Terraform is handed to RuleEngine by S3 reference.
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/parsed/*"]
  }
}

data "aws_iam_policy_document" "rule_engine_parsed_read" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.reports_bucket_arn}/parsed/*"]
  }
}

resource "aws_iam_role_policy" "rule_engine_parsed_read" {
  name   = "${var.name_prefix}-rule-engine-parsed-read"
  role   = aws_iam_role.lambda["rule_engine"].id
  policy = data.aws_iam_policy_document.rule_engine_parsed_read.json
}

resource "aws_iam_role_policy" "ingest_s3_download" {
  name   = "${var.name_prefix}-ingest-s3-download"
  role   = aws_iam_role.lambda["ingest"].id
  policy = data.aws_iam_policy_document.ingest_s3_download.json
}

# Scan (ADR-0048) reads the submitted archive and nothing else: no
# parsed/ or reports/, no tables, no Bedrock. The Trivy process itself
# gets none of these credentials (backend/lambdas/scan/handler.py).
data "aws_iam_policy_document" "scan_s3_read" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.reports_bucket_arn}/uploads/*"]
  }
}

resource "aws_iam_role_policy" "scan_s3_read" {
  name   = "${var.name_prefix}-scan-s3-read"
  role   = aws_iam_role.lambda["scan"].id
  policy = data.aws_iam_policy_document.scan_s3_read.json
}

# The Trivy layer zip is about 51 MB, over Lambda's 50 MB direct-upload
# limit, so it is published from S3. Private, encrypted, versioned bucket
# for build artifacts only.
resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.name_prefix}-artifacts"
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "trivy_layer" {
  bucket = aws_s3_bucket.artifacts.id
  key    = "layers/trivy-${var.trivy_version}.zip"
  source = var.trivy_layer_zip_path
  # source_hash, not etag: a ~51 MB file is uploaded in parts, and S3's
  # etag for a multipart upload is never the file's MD5, so an etag check
  # would re-upload the zip on every apply.
  source_hash = fileexists(var.trivy_layer_zip_path) ? filemd5(var.trivy_layer_zip_path) : null

  depends_on = [aws_s3_bucket_versioning.artifacts]
}

resource "aws_lambda_layer_version" "trivy" {
  layer_name          = "${var.name_prefix}-trivy"
  description         = "Trivy ${var.trivy_version} at /opt/bin/trivy (scripts/build_trivy_layer.py)"
  s3_bucket           = aws_s3_object.trivy_layer.bucket
  s3_key              = aws_s3_object.trivy_layer.key
  compatible_runtimes = ["python3.12"]

  # No s3_object_version on purpose: reading a specific object version
  # needs s3:GetObjectVersion, which the deploy role doesn't have, and it
  # adds nothing. Lambda copies the zip when it publishes, so a published
  # layer version never changes. The hash publishes a new layer version
  # whenever the local zip changes, after the upload above.
  source_code_hash = fileexists(var.trivy_layer_zip_path) ? filebase64sha256(var.trivy_layer_zip_path) : null
}

resource "aws_lambda_function" "this" {
  for_each         = local.lambda_specs
  function_name    = "${var.name_prefix}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  handler          = each.value.handler
  runtime          = "python3.12"
  filename         = each.value.zip
  source_code_hash = fileexists(each.value.zip) ? filebase64sha256(each.value.zip) : null
  timeout          = each.value.timeout
  memory_size      = each.value.memory_size
  layers           = each.key == "scan" ? [aws_lambda_layer_version.trivy.arn] : []

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  # Per-function environment (see local.lambda_environment). Only Ingest
  # calls Guardrails directly (ADR-0033) — Reason's own call happens inside
  # AgentCore Runtime. Audit needs its table name to know where to write.
  dynamic "environment" {
    for_each = contains(keys(local.lambda_environment), each.key) ? [1] : []
    content {
      variables = local.lambda_environment[each.key]
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/states/${var.name_prefix}-review"
  retention_in_days = 90
  tags              = var.tags
}

data "aws_iam_policy_document" "state_machine_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "state_machine" {
  name                 = "${var.name_prefix}-review-state-machine"
  assume_role_policy   = data.aws_iam_policy_document.state_machine_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

data "aws_iam_policy_document" "state_machine_invoke" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = concat([for fn in aws_lambda_function.this : fn.arn], [aws_lambda_function.review_worker.arn])
  }

  statement {
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [var.kill_switch_parameter_arn]
  }

  # The state machine writes to the reviews table directly through SDK
  # integrations, so these grants belong on its role, not a Lambda's:
  # PutItem for the IdempotencyGate conditional write, and UpdateItem for
  # the RecordStage* states that set currentStage before each pipeline
  # stage so GET /reviews/{reviewId} can report progress.
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }

  dynamic "statement" {
    for_each = var.agentcore_runtime_arn == null ? [] : [1]
    content {
      effect  = "Allow"
      actions = ["bedrock-agentcore:InvokeAgentRuntime"]
      # InvokeAgentRuntime is authorized against the runtime-endpoint
      # resource ("runtime/<id>/runtime-endpoint/DEFAULT"), not the bare
      # runtime ARN. Both forms are granted because AWS's docs don't say
      # whether an invocation without an explicit endpoint is ever
      # authorized against the unsuffixed ARN.
      resources = [var.agentcore_runtime_arn, "${var.agentcore_runtime_arn}/runtime-endpoint/*"]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "state_machine_invoke" {
  name   = "${var.name_prefix}-review-state-machine-invoke"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.state_machine_invoke.json
}

# Outer job lifecycle only (ADR-0028): accept/validate/persist input,
# invoke Ingest -> RuleEngine -> the Agent subworkflow once -> Validate ->
# Audit -> Finalize, publish status. The PreflightGate pause/resume and
# Retrieve/Reason loop live inside AgentCore; "InvokeAgent" is a single
# opaque task from this state machine's perspective.
#
# Required StartExecution input. Every field is read through a bare
# "$.xxx" JSONPath somewhere below, and Step Functions raises
# States.Runtime if a referenced path is absent, so none of them are
# optional at the ASL layer even where a handler would tolerate a
# missing key:
#   {
#     "review_id": "...",           # Client-generated UUID, used to poll
#                                    # GET /reviews/{review_id}. Doubles as
#                                    # the idempotency token: IdempotencyGate
#                                    # rejects a second execution for the
#                                    # same review_id before any paid work.
#     "archive_s3_key": "...",       # Key under the reports bucket's
#                                    # uploads/ prefix (ADR-0045). The client
#                                    # gets it from POST /uploads and uploads
#                                    # the archive directly to S3.
#     "terraform_repo_ref": "...",  # Persisted verbatim for display only;
#                                    # the reviewed content is always
#                                    # archive_s3_key.
#     "workload_brief": "...",      # Ingest, then re-used by InvokeAgent
#     "retrieval_query": "...",     # InvokeAgent -> runtime_entrypoint.invoke()
#     "baseline_answers": {}        # InvokeAgent + Audit (pass {} if none)
#   }
# Bucket and table names are not part of this contract: they are
# Terraform-known constants (var.reports_bucket_name, reviews_table_name)
# injected below, so clients never need internal AWS resource names. The
# Audit table name comes from the Lambda's AUDIT_TABLE_NAME environment
# variable.
resource "aws_sfn_state_machine" "review" {
  name     = "${var.name_prefix}-review"
  role_arn = aws_iam_role.state_machine.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = false
    level                  = "ALL"
  }

  # Never place brief, answers, findings or model responses in this state.
  # No automatic retries: a timed-out paid invocation may already be billed.
  definition = jsonencode({
    Comment        = "Identifier-only review workflow; content lives in S3."
    StartAt        = "RunInitial"
    TimeoutSeconds = 604800
    States = {
      RunInitial = {
        Type           = "Task"
        Resource       = aws_lambda_function.review_worker.arn
        TimeoutSeconds = 850
        Parameters = {
          "review_id.$" = "$.review_id"
          phase         = "initial"
        }
        ResultPath = "$.result"
        Next       = "Outcome"
      }
      RunResume = {
        Type           = "Task"
        Resource       = aws_lambda_function.review_worker.arn
        TimeoutSeconds = 850
        Parameters = {
          "review_id.$"  = "$.review_id"
          "resume_key.$" = "$.resume.resume_key"
          phase          = "resume"
        }
        ResultPath = "$.result"
        Next       = "Outcome"
      }
      Outcome = {
        Type = "Choice"
        Choices = [
          { Variable = "$.result.status", StringEquals = "complete", Next = "Complete" },
          { Variable = "$.result.status", StringEquals = "needs_clarification", Next = "StoreClarificationToken" },
          { Variable = "$.result.status", StringEquals = "in_progress", Next = "WaitForStatus" }
        ]
        Default = "ReviewFailed"
      }
      WaitForStatus = {
        Type    = "Wait"
        Seconds = 10
        Next    = "PollStatus"
      }
      PollStatus = {
        Type     = "Task"
        Resource = aws_lambda_function.review_worker.arn
        Parameters = {
          "review_id.$" = "$.review_id"
          phase         = "poll"
        }
        ResultPath = "$.result"
        Next       = "Outcome"
      }
      StoreClarificationToken = {
        Type           = "Task"
        Resource       = "arn:aws:states:::lambda:invoke.waitForTaskToken"
        TimeoutSeconds = 604800
        Parameters = {
          FunctionName = aws_lambda_function.this["store_clarification_token"].arn
          Payload = {
            "review_id.$"       = "$.review_id"
            "taskToken.$"       = "$$.Task.Token"
            reviews_table_name  = var.reviews_table_name
          }
        }
        ResultPath = "$.resume"
        Next       = "RunResume"
      }
      Complete = { Type = "Succeed" }
      ReviewFailed = {
        Type  = "Fail"
        Error = "ReviewProcessingFailed"
        Cause = "The review could not complete. Public status is stored on the review record."
      }
    }
  })

  tags = var.tags
}

# --- Mark failed reviews -------------------------------------------------
# Without this, a failed run would leave the review "pending" forever.
# Step Functions emits an EventBridge event on every terminal status; one
# listener marks the review failed for all of them (Fail states, uncaught
# Lambda errors, timeouts, aborts).

data "aws_iam_policy_document" "mark_review_failed_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.reviews_table_arn]
  }
}

resource "aws_iam_role" "mark_review_failed" {
  name                 = "${var.name_prefix}-mark-review-failed"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy_attachment" "mark_review_failed_logs" {
  role       = aws_iam_role.mark_review_failed.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "mark_review_failed_access" {
  name   = "${var.name_prefix}-mark-review-failed-access"
  role   = aws_iam_role.mark_review_failed.id
  policy = data.aws_iam_policy_document.mark_review_failed_access.json
}

resource "aws_lambda_function" "mark_review_failed" {
  function_name    = "${var.name_prefix}-mark-review-failed"
  role             = aws_iam_role.mark_review_failed.arn
  handler          = "backend.lambdas.mark_review_failed.handler.handler"
  runtime          = "python3.12"
  filename         = var.mark_review_failed_zip_path
  source_code_hash = fileexists(var.mark_review_failed_zip_path) ? filebase64sha256(var.mark_review_failed_zip_path) : null
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      REVIEWS_TABLE_NAME = var.reviews_table_name
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "review_execution_failed" {
  name        = "${var.name_prefix}-review-execution-failed"
  description = "Review state machine reached FAILED, TIMED_OUT, or ABORTED."
  event_pattern = jsonencode({
    source        = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      stateMachineArn = [aws_sfn_state_machine.review.arn]
      status          = ["FAILED", "TIMED_OUT", "ABORTED"]
    }
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "review_execution_failed" {
  rule = aws_cloudwatch_event_rule.review_execution_failed.name
  arn  = aws_lambda_function.mark_review_failed.arn
}

resource "aws_lambda_permission" "events_invoke_mark_review_failed" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mark_review_failed.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.review_execution_failed.arn
}
