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
    actions   = ["s3:GetObject"]
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
    actions   = ["s3:GetObject"]
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
    actions   = ["s3:GetObject"]
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
    resources = [for fn in aws_lambda_function.this : fn.arn]
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
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "ArchiBrief review pipeline outer job lifecycle (ADR-0028)"
    StartAt = "IdempotencyGate"
    States = {
      # A retried or duplicated POST /reviews for the same review_id must
      # not re-run paid work (Bedrock calls in particular). A conditional
      # PutItem is the standard pure-ASL idempotency pattern for a direct
      # API Gateway -> Step Functions integration with no BFF Lambda
      # (ADR-0016/0042): the first execution to claim a review_id wins, and
      # any later one fails the condition and stops before any paid work.
      # It can't change the HTTP response (StartExecution has already
      # returned 200 by the time this runs); it only prevents duplicate
      # work and cost.
      IdempotencyGate = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:putItem"
        Parameters = {
          TableName = var.reviews_table_name
          Item = {
            reviewId       = { "S.$" = "$.review_id" }
            idempotencyKey = { "S.$" = "$.review_id" }
            status         = { S = "pending" }
            createdAt      = { "S.$" = "$$.State.EnteredTime" }
            # Persisted so get_review/build_review_report can return the
            # submitted value (backend/shared/report.py). Always present:
            # terraform_repo_ref is a required input field (see above).
            terraformRepoRef = { "S.$" = "$.terraform_repo_ref" }
          }
          ConditionExpression = "attribute_not_exists(reviewId)"
        }
        ResultPath = "$.idempotencyResult"
        Catch = [
          {
            ErrorEquals = ["DynamoDB.ConditionalCheckFailedException"]
            ResultPath  = "$.idempotencyError"
            Next        = "DuplicateReviewSubmission"
          }
        ]
        Next = "CheckKillSwitch"
      }
      # Succeed, not Fail: this execution is correctly declining to redo
      # paid work. The review's real status comes from the first execution
      # and is visible through GET /reviews/{review_id}.
      DuplicateReviewSubmission = {
        Type = "Succeed"
      }
      # ADR-0030's "fast application kill switch checked before paid work
      # starts": fails immediately, before Ingest/RuleEngine/Bedrock, so
      # a real incident stops new billed work without waiting on AWS
      # Budgets (which has no native action to halt Bedrock spend).
      CheckKillSwitch = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:ssm:getParameter"
        Parameters = {
          Name = var.kill_switch_parameter_name
        }
        ResultPath = "$.killSwitch"
        Next       = "KillSwitchGate"
      }
      KillSwitchGate = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.killSwitch.Parameter.Value"
            StringEquals = "true"
            Next         = "KillSwitchActive"
          }
        ]
        Default = "RecordStageIngest"
      }
      KillSwitchActive = {
        Type  = "Fail"
        Error = "KillSwitchActive"
        Cause = "ADR-0030 application kill switch is set to true — no new paid work starts until it's reset."
      }
      # RecordStage* states: a direct DynamoDB UpdateItem before each
      # pipeline stage, writing currentStage onto the review's item. A
      # separate Task per stage rather than a write inside each Lambda,
      # because Ingest/RuleEngine/Validate don't receive review_id or the
      # table name, while review_id stays at the top level of state for
      # the whole execution (every Task merges its result under a
      # namespaced ResultPath). ResultPath = null discards the UpdateItem
      # response. currentStage values are internal names; the frontend
      # (lib/progress.ts) maps them to generic user-facing labels.
      RecordStageIngest = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "ingest" }
          }
        }
        ResultPath = null
        Next       = "Ingest"
      }
      # ResultPath merges Ingest's return ({status, resources, variables,
      # files_parsed, not_observable, workload_brief,
      # guardrails_decisions}) under $.ingestResult. Without it the result
      # would replace state and drop review_id and the rest of the input.
      # report_bucket is a Terraform-known constant injected as a literal,
      # never caller-supplied (ADR-0045).
      Ingest = {
        Type     = "Task"
        Resource = aws_lambda_function.this["ingest"].arn
        Parameters = {
          "archive_s3_key.$" = "$.archive_s3_key"
          "workload_brief.$" = "$.workload_brief"
          "report_bucket"    = var.reports_bucket_name
          # Ingest writes the parsed tree to parsed/<review_id>.json and
          # returns only a reference, since workflow state caps at 256 KiB.
          "review_id.$" = "$.review_id"
        }
        ResultPath = "$.ingestResult"
        Next       = "IngestResponseGate"
      }
      # Halts on Ingest status "rejected" (path traversal, symlink, too
      # many members, or no parseable .tf files) or "blocked" (a
      # Guardrails hit on the workload brief, ADR-0033). Otherwise
      # RuleEngine would run on empty resources and the review would
      # "succeed" with zero findings and no explanation.
      IngestResponseGate = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.ingestResult.status"
            StringEquals = "rejected"
            Next         = "IngestRejected"
          },
          {
            Variable     = "$.ingestResult.status"
            StringEquals = "blocked"
            Next         = "IngestBlocked"
          }
        ]
        Default = "Scan"
      }
      # Trivy over the submitted Terraform (ADR-0048). Never fails the
      # review: the Lambda reports problems as status "unavailable", and
      # the Catch covers the Lambda itself failing (timeout, throttling).
      # Either way RuleEngine falls back to ArchiBrief's own rules and
      # the report says the scanner didn't run.
      Scan = {
        Type     = "Task"
        Resource = aws_lambda_function.this["scan"].arn
        Parameters = {
          "review_id.$"      = "$.review_id"
          "archive_s3_key.$" = "$.archive_s3_key"
          "report_bucket"    = var.reports_bucket_name
        }
        ResultPath = "$.scanResult"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.scanError"
            Next        = "ScanUnavailable"
          }
        ]
        Next = "RecordStageRuleEngine"
      }
      ScanUnavailable = {
        Type       = "Pass"
        Result     = { status = "unavailable", tool = "trivy", reason = "scan_step_failed" }
        ResultPath = "$.scanResult"
        Next       = "RecordStageRuleEngine"
      }
      RecordStageRuleEngine = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "rule_engine" }
          }
        }
        ResultPath = null
        Next       = "RuleEngine"
      }
      IngestRejected = {
        Type  = "Fail"
        Error = "IngestRejected"
        Cause = "Ingest rejected the submitted Terraform archive (path traversal, a symlink, too many members, or no parseable .tf files) — see this execution's Ingest Task input/output in CloudWatch Logs for the specific reason."
      }
      IngestBlocked = {
        Type  = "Fail"
        Error = "IngestBlocked"
        Cause = "Ingest's inline Guardrails check (ADR-0033) blocked the workload brief before any paid reasoning work started."
      }
      # RuleEngine loads the parsed Terraform from the S3 reference Ingest
      # returned (backend/lambdas/rule_engine/handler.py's load_parsed), so
      # the full tree never travels through workflow state.
      RuleEngine = {
        Type     = "Task"
        Resource = aws_lambda_function.this["rule_engine"].arn
        Parameters = {
          "review_id.$"     = "$.review_id"
          "parsed_s3_key.$" = "$.ingestResult.parsed_s3_key"
          "report_bucket"   = var.reports_bucket_name
          "scanner.$"       = "$.scanResult"
        }
        ResultPath = "$.ruleEngineResult"
        Next       = "InitEffectiveInput"
      }
      # backend/agent/runtime_entrypoint.py's invoke() requires review_id,
      # workload_brief and retrieval_query, and optionally takes
      # baseline_answers and rule_findings. PrepareAgentInput assembles
      # exactly that object into $.agentInput from the execution input and
      # RuleEngine's output (whose findings live at
      # $.ruleEngineResult.findings).
      # $.effective holds the review's current brief + answers, folded
      # forward across clarification rounds (ApplyClarification below), so
      # Reason, Audit, and Finalize all see the same context and a second
      # round keeps the first round's answers. rounds bounds how many times
      # a review may pause for clarification.
      InitEffectiveInput = {
        Type = "Pass"
        Parameters = {
          "workload_brief.$"   = "$.workload_brief"
          "baseline_answers.$" = "$.baseline_answers"
          "rounds"             = 0
        }
        ResultPath = "$.effective"
        Next       = "PrepareAgentInput"
      }
      PrepareAgentInput = {
        Type = "Pass"
        Parameters = {
          "review_id.$"                  = "$.review_id"
          "workload_brief.$"             = "$.effective.workload_brief"
          "baseline_answers.$"           = "$.effective.baseline_answers"
          "retrieval_query.$"            = "$.retrieval_query"
          "rule_findings.$"              = "$.ruleEngineResult.findings"
          "deterministic_rule_version.$" = "$.ruleEngineResult.rule_version"
          # What the Terraform declares, so Reason doesn't guess.
          "terraform_resources.$" = "$.ruleEngineResult.resource_summary"
        }
        ResultPath = "$.agentInput"
        Next       = "RecordStageReasoning"
      }
      # Reached from PrepareAgentInput on both the first pass and every
      # pass after a clarification round.
      RecordStageReasoning = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "reasoning" }
          }
        }
        ResultPath = null
        Next       = "InvokeAgent"
      }
      InvokeAgent = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
        Parameters = {
          # Amazon States Language requires a string here, not null.
          # agentcore_runtime_arn defaults to null, which would fail ASL
          # validation at CreateStateMachine, so a placeholder lets the
          # state machine be created; InvokeAgent fails at execution time
          # until a real AgentCore Runtime ARN is supplied.
          "AgentRuntimeArn" = coalesce(var.agentcore_runtime_arn, "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/not-yet-deployed")
          # Payload is a raw string field. States.JsonToString serializes
          # only the curated $.agentInput object, not the whole state with
          # its workflow bookkeeping keys (killSwitch, ingestResult).
          "Payload.$" = "States.JsonToString($.agentInput)"
          # AgentCore requires a session ID with a minimum length (33
          # characters) that a short review_id might not meet, so a fixed
          # prefix guarantees the floor whatever the review_id format.
          "RuntimeSessionId.$" = "States.Format('archibrief-review-session-{}', $.review_id)"
        }
        # Merged under $.agentResult rather than replacing state.
        ResultPath = "$.agentResult"
        # Without TimeoutSeconds a Task state is effectively unbounded
        # (99999999 seconds), so a hung Bedrock call or stuck runtime would
        # hold the execution open indefinitely. 300 seconds is a generous
        # ceiling; max_tokens and retrieval limits already bound the work
        # inside runtime_entrypoint.py, and this only bounds the outer
        # wall-clock wait.
        TimeoutSeconds = 300
        Catch = [
          {
            ErrorEquals = ["States.Timeout"]
            ResultPath  = "$.agentTimeoutError"
            Next        = "AgentInvocationTimedOut"
          }
        ]
        Next = "ParseAgentResponse"
      }
      # An exceeded bounded wait is an expected terminal outcome, not a
      # transient fault worth retrying.
      AgentInvocationTimedOut = {
        Type  = "Fail"
        Error = "AgentInvocationTimedOut"
        Cause = "InvokeAgent did not complete within 300 seconds — see this execution's history in CloudWatch for where the AgentCore Runtime invocation stalled."
      }
      # The SDK integration returns the response body at
      # $.agentResult.Response (capital R) as a raw JSON string, which must
      # be parsed with States.StringToJson before its fields are reachable.
      # ASL can't chain a property access onto an intrinsic's result, so
      # parsing gets its own Pass state; AgentResponseGate and Validate read
      # the resulting $.agentParsed.parsed object.
      ParseAgentResponse = {
        Type = "Pass"
        Parameters = {
          "parsed.$" = "States.StringToJson($.agentResult.Response)"
        }
        ResultPath = "$.agentParsed"
        Next       = "AgentResponseGate"
      }
      # invoke() can return {"status": "needs_clarification", ...} with no
      # "findings" key when PreflightGate pauses for a required field.
      # That is an expected, non-failure outcome, and Validate needs
      # findings, so it routes to the clarification pause instead.
      AgentResponseGate = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.agentParsed.parsed.status"
            StringEquals = "needs_clarification"
            Next         = "StoreClarificationToken"
          }
        ]
        Default = "RecordStageValidate"
      }
      RecordStageValidate = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "validate" }
          }
        }
        ResultPath = null
        Next       = "Validate"
      }
      # Pauses through the lambda:invoke.waitForTaskToken pattern:
      # store_clarification_token.handler persists the task token on the
      # review's DynamoDB item and returns immediately, but this state
      # doesn't complete until clarify_review.handler (behind
      # POST /reviews/{reviewId}/clarify) calls SendTaskSuccess with that
      # token once a human answers. A Lambda is used because DynamoDB and
      # Bedrock AgentCore integrations don't support waitForTaskToken.
      #
      # TimeoutSeconds bounds the wait at 7 days; ASL's default would let
      # it wait essentially forever. A timed-out clarification is a
      # terminal outcome, not a transient fault worth retrying.
      StoreClarificationToken = {
        Type           = "Task"
        Resource       = "arn:aws:states:::lambda:invoke.waitForTaskToken"
        TimeoutSeconds = 604800
        Parameters = {
          FunctionName = aws_lambda_function.this["store_clarification_token"].arn
          Payload = {
            "review_id.$"           = "$.review_id"
            "taskToken.$"           = "$$.Task.Token"
            "needs_clarification.$" = "$.agentParsed.parsed.needs_clarification"
            "preflight_fields.$"    = "$.agentParsed.parsed.preflight_fields"
            # Passed as a literal Parameter, the same convention
            # Audit/Finalize use below.
            "reviews_table_name" = var.reviews_table_name
          }
        }
        ResultPath = "$.clarificationAnswer"
        Catch = [
          {
            ErrorEquals = ["States.Timeout"]
            ResultPath  = "$.clarificationError"
            Next        = "ClarificationTimedOut"
          }
        ]
        Next = "ApplyClarification"
      }
      ClarificationTimedOut = {
        Type  = "Fail"
        Error = "ClarificationTimedOut"
        Cause = "No answer was submitted via POST /reviews/{reviewId}/clarify within the 7-day window."
      }
      # Folds this round's answers and note into $.effective: answers merge
      # over earlier rounds (later wins per field), the note is appended to
      # the brief that Reason reads and Finalize persists.
      ApplyClarification = {
        Type = "Pass"
        Parameters = {
          "workload_brief.$"   = "States.Format('{}{}', $.effective.workload_brief, $.clarificationAnswer.clarification_note)"
          "baseline_answers.$" = "States.JsonMerge($.effective.baseline_answers, $.clarificationAnswer.baseline_answers, false)"
          "rounds.$"           = "States.MathAdd($.effective.rounds, 1)"
        }
        ResultPath = "$.effective"
        Next       = "ClarificationRoundGate"
      }
      ClarificationRoundGate = {
        Type = "Choice"
        Choices = [
          {
            Variable           = "$.effective.rounds"
            NumericGreaterThan = var.max_clarification_rounds
            Next               = "ClarificationLimitReached"
          }
        ]
        Default = "PrepareAgentInput"
      }
      ClarificationLimitReached = {
        Type  = "Fail"
        Error = "ClarificationLimitReached"
        Cause = "The review asked for clarification more times than max_clarification_rounds allows."
      }
      Validate = {
        Type     = "Task"
        Resource = aws_lambda_function.this["validate"].arn
        # backend/lambdas/validate/handler.py reads event["findings"],
        # taken from ParseAgentResponse's parsed object.
        Parameters = {
          "findings.$" = "$.agentParsed.parsed.findings"
        }
        # Merges {status, valid_findings, rejected_count, rejected} under
        # $.validateResult rather than replacing state.
        ResultPath = "$.validateResult"
        Next       = "RecordStageAudit"
      }
      RecordStageAudit = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "audit" }
          }
        }
        ResultPath = null
        Next       = "Audit"
      }
      # backend/lambdas/audit/handler.py's AuditLogEntry requires
      # review_id; the other fields are optional (read with event.get).
      # baseline_answers comes from $.effective (including clarification
      # rounds), guardrails_decisions from Ingest's inline check, and
      # deterministic_rule_version from RuleEngine. corpus_version and
      # model_id have no source in this state machine and are left absent
      # rather than guessed.
      Audit = {
        Type     = "Task"
        Resource = aws_lambda_function.this["audit"].arn
        Parameters = {
          "review_id.$"                  = "$.review_id"
          "baseline_answers.$"           = "$.effective.baseline_answers"
          "guardrails_decisions.$"       = "$.ingestResult.guardrails_decisions"
          "deterministic_rule_version.$" = "$.ruleEngineResult.rule_version"
        }
        ResultPath = "$.auditResult"
        Next       = "RecordStageFinalize"
      }
      RecordStageFinalize = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:updateItem"
        Parameters = {
          TableName = var.reviews_table_name
          Key = {
            reviewId = { "S.$" = "$.review_id" }
          }
          UpdateExpression = "SET currentStage = :stage"
          ExpressionAttributeValues = {
            ":stage" = { S = "finalize" }
          }
        }
        ResultPath = null
        Next       = "Finalize"
      }
      # backend/lambdas/finalize/handler.py requires review_id and
      # findings. findings is Validate's valid_findings (the
      # schema-validated list, not the agent's raw output), per ADR-0022's
      # layer ordering. report_bucket and reviews_table_name are literal
      # Terraform values, never part of the caller's request.
      # workload_brief is written to the evidence ledger in S3, the source
      # of truth for full review content (ADR-0007/0042), because
      # deeper_review.handler (the "go deeper" endpoint) needs it later to
      # re-invoke Reason. preflight_fields and defaults_version persist the
      # completed review's baseline answers (ADR-0031);
      # $.agentParsed.parsed is whichever InvokeAgent response completed
      # the review, including a retry after a clarification round.
      Finalize = {
        Type     = "Task"
        Resource = aws_lambda_function.this["finalize"].arn
        Parameters = {
          "review_id.$" = "$.review_id"
          "findings.$"  = "$.validateResult.valid_findings"
          # Effective brief: includes any clarification notes, so "go
          # deeper" later reasons over the same context.
          "workload_brief.$"   = "$.effective.workload_brief"
          "preflight_fields.$" = "$.agentParsed.parsed.preflight_fields"
          "defaults_version.$" = "$.agentParsed.parsed.defaults_version"
          # Feeds compute_cost_estimate_tier. Always present here:
          # IngestResponseGate routes rejected/blocked results to a Fail
          # state before Finalize can run.
          "resource_count.$" = "$.ingestResult.resource_count"
          # ADR-0049's summary, stored in the ledger for the report chat
          # (ADR-0050). RuleEngine always runs before Finalize.
          "terraform_resources.$" = "$.ruleEngineResult.resource_summary"
          # The report's diagram; Finalize places the final findings on it.
          "architecture.$"     = "$.ruleEngineResult.architecture"
          "report_bucket"      = var.reports_bucket_name
          "reviews_table_name" = var.reviews_table_name
        }
        End = true
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
