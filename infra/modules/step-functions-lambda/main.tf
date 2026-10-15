# Terraform module: step-functions-lambda
# Step Functions (Standard) owns only the durable outer job lifecycle —
# accept, validate, persist input, invoke the agent stage once,
# validate/persist result, publish status (ADR-0028). Each bounded
# stateless Lambda (Ingest, RuleEngine, Validate, Audit, Finalize) gets
# its own least-privilege execution role defined right here, in the same
# module as the Lambda itself (ADR-0021) — never a shared/generic role.
# The one reasoning/retrieval subworkflow runs in AgentCore Runtime, not
# duplicated here — the state machine below calls it once via an AWS SDK
# integration task, referencing an already-deployed AgentCore Runtime
# (agentcore_runtime_arn) that doesn't exist until account bootstrap.

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
  }

  # `timeout` added 2026-10-12, live-tested: none of these Lambdas ever
  # had an explicit timeout, so every one of them silently ran on AWS
  # Lambda's bare 3-second default (confirmed directly — Ingest's
  # CloudWatch log showed "Status: timeout" at exactly 3000.00 ms, with
  # no exception/traceback, because it was genuinely still working: S3
  # download + inline Guardrails check + hcl2 parsing all take longer
  # than 3s). The api-gateway module's Lambdas already set this
  # explicitly per function (create_upload=5, deeper_review=60, etc.) —
  # this module just never did. Ingest gets the most generous value
  # (network + Bedrock call); rule_engine/validate are pure in-memory
  # compute; audit/finalize/store_clarification_token each do one or two
  # DynamoDB/S3 calls.
  #
  # `memory_size` added 2026-10-12, same live-testing session, same root
  # cause as the timeout gap above: nobody ever set it either, so every
  # one of these ran on AWS Lambda's bare 128 MB default. Lambda's CPU
  # allocation scales with configured memory — at 128 MB a function gets
  # a small fraction of one vCPU. Confirmed by direct reproduction: the
  # exact 317-byte main.tf that hung Ingest for the full 30s timeout
  # (stage-tracing showed it got stuck inside parse_terraform_files's
  # hcl2.load() call, right after extraction) parses in ~38ms on a normal
  # dev machine with the identical hcl2/lark versions — the code and
  # input were never the problem, Ingest was just CPU-starved running
  # lark's Earley-parser grammar at 128 MB. Ingest gets the most (HCL
  # parsing via lark is real CPU work, on top of the S3 download and
  # Bedrock Guardrails call); the rest get a moderate bump over the
  # 128 MB default since none of them had ever been sized deliberately.
  lambda_specs = {
    ingest      = { handler = "backend.lambdas.ingest.handler.handler", zip = var.lambda_zip_paths.ingest, timeout = 30, memory_size = 1024 }
    rule_engine = { handler = "backend.lambdas.rule_engine.handler.handler", zip = var.lambda_zip_paths.rule_engine, timeout = 10, memory_size = 256 }
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

# RuleEngine/Validate are pure compute on their event payload — no
# direct DynamoDB/S3/Bedrock access needed beyond CloudWatch Logs.
data "aws_iam_policy_document" "audit_finalize_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem"]
    resources = [var.reviews_table_arn, var.audit_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.reports_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "audit_finalize_data_access" {
  for_each = toset(["audit", "finalize"])
  name     = "${var.name_prefix}-${each.key}-data-access"
  role     = aws_iam_role.lambda[each.key].id
  policy   = data.aws_iam_policy_document.audit_finalize_data_access.json
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

# Ingest calls Guardrails inline (ADR-0033) — see the Ingest Lambda's
# handler and its GUARDRAIL_ID/GUARDRAIL_VERSION environment variables
# above. Always created: this module's caller (infra/environments/dev)
# always wires a real module.guardrails output here, so guardrail_id is
# never actually optional in practice — a count/for_each conditioned on
# it would depend on a value unknown until apply (the guardrail doesn't
# exist yet on a fresh account) and Terraform can't plan a resource
# count from an unknown value. See Work-Project-Issues-Log.md, 2026-09-09.
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

# Added 2026-10-12 (ADR-0045, direct-upload archive_path design) —
# Ingest now downloads the client's already-uploaded archive from S3
# (backend/lambdas/ingest/handler.py's _resolve_archive_path) instead of
# requiring a local archive_path the client could never actually supply.
# Scoped to the "uploads/" prefix only — the same prefix create_upload's
# presigned POST (infra/modules/api-gateway) is scoped to write into,
# never the whole reports bucket (which also holds Finalize's trusted
# evidence ledgers, a different trust level of content entirely).
data "aws_iam_policy_document" "ingest_s3_download" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reports_bucket_arn}/uploads/*"]
  }
}

resource "aws_iam_role_policy" "ingest_s3_download" {
  name   = "${var.name_prefix}-ingest-s3-download"
  role   = aws_iam_role.lambda["ingest"].id
  policy = data.aws_iam_policy_document.ingest_s3_download.json
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

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  # Per-function environment (see local.lambda_environment). Only Ingest
  # calls Guardrails directly (ADR-0033) — Reason's own call happens inside
  # AgentCore Runtime. Audit needs its table name, or it would have nowhere
  # to write (Codex F13).
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

  # For the new leading IdempotencyGate Task (2026-09-17 fix) — a
  # conditional PutItem, called directly by the state machine's own SDK
  # integration (not by any Lambda), so this permission belongs on the
  # state machine's role, not the Finalize Lambda's own
  # audit_finalize_data_access statement (which already covers Finalize's
  # separate, later PutItem call).
  #
  # dynamodb:UpdateItem added 2026-10-13 for the new RecordStage* states
  # (below) — a direct SDK UpdateItem call before each real pipeline
  # stage, writing "currentStage" onto the review's existing item so
  # GET /reviews/{reviewId} can report real progress instead of just
  # "pending"/"needs_clarification"/"complete". Same resource as the
  # PutItem grant above — one table, two different direct-SDK write
  # patterns from the state machine's own role.
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
      # Found 2026-10-12, live-tested: a real InvokeAgentRuntime call is
      # authorized against the RUNTIME-ENDPOINT resource
      # ("runtime/<id>/runtime-endpoint/DEFAULT" — confirmed via the
      # actual AccessDeniedException's resource ARN), not the bare
      # runtime ARN this statement granted on exact-match alone. The
      # permissions boundary's own AllowAgentCoreInvoke statement already
      # used a wildcard ("runtime/*") and would have allowed this; it was
      # this identity policy's own exact-match Resource that was too
      # narrow. Granting both forms since AWS's docs don't pin down
      # whether a bare-ARN invocation (no explicit endpoint) is ever
      # authorized against the unsuffixed ARN directly.
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

# Outer job lifecycle only (ADR-0028) — accept/validate/persist input,
# invoke Ingest -> RuleEngine -> the Agent subworkflow once -> Validate ->
# Audit -> Finalize, publish status. The PreflightGate pause/resume and
# Retrieve/Reason loop live inside AgentCore, not duplicated as states
# here — "InvokeAgent" is a single opaque task from this state machine's
# perspective.
#
# REQUIRED StartExecution Input shape (2026-09-17 fix — every field below
# is read via a bare "$.xxx" JSONPath somewhere in this definition, and
# Step Functions raises a States.Runtime error if a referenced path is
# absent, so none of these are truly optional at the ASL layer even where
# the Lambda handler itself would tolerate a missing key via .get()):
#   {
#     "review_id": "...",           # client-generated (a UUID the client
#                                    # already needs, to poll GET
#                                    # /reviews/{review_id} afterward — see
#                                    # api-gateway module's TODO for that
#                                    # route). Doubles as the idempotency
#                                    # token: IdempotencyGate below rejects
#                                    # a second execution for the same
#                                    # review_id before any paid work runs.
#     "archive_s3_key": "...",       # Ingest downloads this from the
#                                    # reports bucket's "uploads/" prefix
#                                    # (ADR-0045, 2026-10-12) — the client
#                                    # gets this key from POST /uploads'
#                                    # presigned-POST response after
#                                    # uploading its own archive directly
#                                    # to S3, never through this API.
#                                    # Replaces the old "archive_path"
#                                    # field, which no client could ever
#                                    # have correctly supplied (no path on
#                                    # this Lambda's own ephemeral
#                                    # filesystem is meaningful to a
#                                    # remote caller).
#     "terraform_repo_ref": "...",  # IdempotencyGate only, persisted
#                                    # verbatim for display — informational
#                                    # only, not consumed by Ingest; the
#                                    # real archive content is always
#                                    # archive_s3_key, regardless of what
#                                    # this string says.
#     "workload_brief": "...",      # Ingest, then re-used by InvokeAgent
#     "retrieval_query": "...",     # InvokeAgent -> runtime_entrypoint.invoke()
#     "baseline_answers": {}        # InvokeAgent + Audit (pass {} if none)
#   }
# report_bucket/reviews_table_name are DELIBERATELY NOT part of this
# contract (removed 2026-09-17, see Work-Project-Issues-Log.md) — they're
# Terraform-known infra constants (var.reports_bucket_name/
# reviews_table_name), not caller-supplied input; requiring the client to
# know real internal AWS resource names was a real bug, not a design
# choice. The Audit table name likewise comes from the Lambda's
# AUDIT_TABLE_NAME environment variable, not the execution input.
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
      # New state (2026-09-17 fix): a retried/duplicated POST /reviews for
      # the same client-supplied review_id must not re-run paid work
      # (Bedrock calls in particular) a second time. A conditional PutItem
      # is the standard pure-ASL idempotency pattern for a direct API
      # Gateway -> Step Functions integration with no BFF Lambda
      # (ADR-0016/0042) — first execution to claim a given review_id wins,
      # any later one for the same ID fails the condition and short-
      # circuits before CheckKillSwitch/Ingest/RuleEngine/InvokeAgent ever
      # run. Note this can't change the original HTTP response (StartExecution
      # itself already returned 200 with an execution ARN before this task
      # runs — that's inherent to the async AWS_PROXY integration, not a
      # gap in this fix) — its value is purely cost/duplicate-work
      # protection, not client-visible dedup signaling.
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
            # Persisted 2026-10-01 so get_review/build_review_report can
            # return the client's real submitted value instead of a
            # flagged placeholder (see backend/shared/report.py and
            # Work-Project-Issues-Log.md). terraform_repo_ref is now a
            # required field in the StartExecution Input contract (see
            # comment block above), so this reference is always present.
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
      # Succeeds (not Fails) — a duplicate submission isn't an error
      # condition for the ALREADY-RETURNED HTTP response, it's this
      # second execution correctly declining to redo paid work. Real
      # status (from the first, real execution) is only ever visible via
      # GET /reviews/{review_id}, never this execution's own outcome.
      DuplicateReviewSubmission = {
        Type = "Succeed"
      }
      # ADR-0030's "fast application kill switch checked before paid work
      # starts" — fails immediately, before Ingest/RuleEngine/Bedrock, so
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
      # RecordStage* states (added 2026-10-13) — a direct DynamoDB
      # UpdateItem SDK call immediately before each real pipeline stage,
      # writing "currentStage" onto the review's existing item.
      # Deliberately a separate Task per stage rather than folding this
      # into each stage's own Lambda: Ingest/RuleEngine/Validate don't
      # currently receive review_id/reviews_table_name in their event
      # (only Audit/Finalize/StoreClarificationToken do), and review_id
      # is already present at the top level of state throughout this
      # whole execution (every real Task's ResultPath merges its result
      # under a namespaced key, never replacing top-level state — see
      # Ingest's own ResultPath comment below) — so a stage-agnostic
      # UpdateItem keyed on $.review_id works identically everywhere
      # without threading a new field through every Lambda's Parameters.
      # ResultPath = null discards the UpdateItem response entirely
      # rather than merging it into state (ASL's documented meaning for
      # a null ResultPath), since nothing downstream ever needs it.
      # currentStage values are internal stage names, not user-facing
      # copy — the frontend (lib/progress.ts) maps each one to a small
      # set of generic macro-stage labels plus a friendlier micro-step
      # description, deliberately not exposing these literal names or
      # this project's internal pipeline structure to the browser.
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
      # Fixed 2026-09-16 (Codex review, re-verified directly against
      # backend/lambdas/ingest/handler.py): Ingest's raw return
      # ({status, resources, variables, files_parsed, not_observable,
      # workload_brief, guardrails_decisions}) used to REPLACE state
      # entirely (no ResultPath) — losing review_id and everything else
      # the original execution input carried before RuleEngine even ran.
      # ResultPath merges it under $.ingestResult instead, alongside the
      # untouched original input.
      # Added an explicit Parameters block 2026-10-12 (ADR-0045) — Ingest
      # previously received the whole state implicitly (no Parameters at
      # all), which worked only because archive_path was never a real,
      # client-suppliable field in the first place (no client can know a
      # path meaningful inside this Lambda's own ephemeral filesystem).
      # report_bucket is a Terraform-known infra constant injected as a
      # literal, same reasoning as Finalize's own report_bucket Parameter
      # below — never caller-supplied (see that Parameters block's own
      # comment for the 2026-09-17 fix this mirrors).
      Ingest = {
        Type     = "Task"
        Resource = aws_lambda_function.this["ingest"].arn
        Parameters = {
          "archive_s3_key.$" = "$.archive_s3_key"
          "workload_brief.$" = "$.workload_brief"
          "report_bucket"    = var.reports_bucket_name
        }
        ResultPath = "$.ingestResult"
        Next       = "IngestResponseGate"
      }
      # New state (2026-10-01 fix): this was the exact follow-up flagged
      # by name in the 2026-09-16 comment this replaces — Ingest returning
      # status "rejected" (IngestRejected: path traversal, symlink, too
      # many members, or no parseable .tf files) or "blocked" (a
      # Guardrails hit on the workload brief, ADR-0033) used to fall
      # through to RuleEngine silently, which just produced zero findings
      # from a now-empty $.ingestResult.resources rather than halting with
      # a clear reason — a real review would complete "successfully" with
      # no findings and no indication why. Mirrors AgentResponseGate's own
      # Choice-state pattern below.
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
        Default = "RecordStageRuleEngine"
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
      # RuleEngine's handler reads event["parsed"] and event["review_id"]
      # directly (backend/lambdas/rule_engine/handler.py) — neither name
      # exists at top level once Ingest's output moved to $.ingestResult
      # above. Parameters rebuilds RuleEngine's input explicitly: the
      # whole $.ingestResult dict already has the "resources"/"variables"
      # shape rule_engine.py's _resources() helper expects under the key
      # "parsed", so it's aliased wholesale rather than field-by-field.
      RuleEngine = {
        Type     = "Task"
        Resource = aws_lambda_function.this["rule_engine"].arn
        Parameters = {
          "review_id.$" = "$.review_id"
          "parsed.$"    = "$.ingestResult"
        }
        ResultPath = "$.ruleEngineResult"
        Next       = "PrepareAgentInput"
      }
      # New state (2026-09-16 fix): backend/agent/runtime_entrypoint.py's
      # invoke() reads payload["review_id"], payload["workload_brief"],
      # payload["retrieval_query"] (all required — bare dict indexing,
      # not .get()), plus optional baseline_answers and rule_findings
      # (payload.get("rule_findings", [])). None of those survive as a
      # flat object after RuleEngine's own ResultPath merge above (its
      # findings live at $.ruleEngineResult.findings, named "findings"
      # not "rule_findings"). This Pass state assembles exactly the
      # object InvokeAgent's Payload needs into $.agentInput, pulling
      # review_id/workload_brief/retrieval_query/baseline_answers from
      # the original execution input (see the required-input contract
      # comment above aws_sfn_state_machine.review) and rule_findings/
      # deterministic_rule_version from RuleEngine's output.
      PrepareAgentInput = {
        Type = "Pass"
        Parameters = {
          "review_id.$"                  = "$.review_id"
          "workload_brief.$"             = "$.workload_brief"
          "baseline_answers.$"           = "$.baseline_answers"
          "retrieval_query.$"            = "$.retrieval_query"
          "rule_findings.$"              = "$.ruleEngineResult.findings"
          "deterministic_rule_version.$" = "$.ruleEngineResult.rule_version"
        }
        ResultPath = "$.agentInput"
        Next       = "RecordStageReasoning"
      }
      # Shared by both PrepareAgentInput and PrepareAgentInputAfterClarification
      # below — ASL allows multiple states to transition into the same
      # next state, and "reasoning" means the same thing on either path
      # into InvokeAgent.
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
          # AgentCore Runtime isn't deployed yet (agentcore_runtime_arn
          # defaults to null in tfvars) — a real apply against a null
          # value would fail ASL schema validation at CreateStateMachine.
          # This placeholder lets the state machine itself be created
          # now; the InvokeAgent task will fail at actual execution time
          # until a real AgentCore Runtime ARN is supplied — deliberate,
          # documented deferral, see Work-Project-Issues-Log.md.
          "AgentRuntimeArn" = coalesce(var.agentcore_runtime_arn, "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/not-yet-deployed")
          # Payload is a raw byte/string field, not a nested JSON
          # structure — States.JsonToString serializes PrepareAgentInput's
          # curated $.agentInput object (not the whole state, which would
          # include boto3-unrelated Step Functions bookkeeping keys like
          # killSwitch/ingestResult that runtime_entrypoint.py neither
          # needs nor expects).
          "Payload.$" = "States.JsonToString($.agentInput)"
          # AgentCore requires a stable session ID for correlation; AWS's
          # docs (checked, not just Codex's claim) specify a minimum
          # length (commonly cited as 33 characters) that a short
          # review_id alone might not satisfy — States.Format prepends a
          # fixed literal to guarantee a floor length regardless of the
          # real review_id format, which isn't fully pinned down yet
          # (validate_reason_node.py's test id is ~30 chars; production
          # review_id's real format isn't confirmed in this codebase).
          "RuntimeSessionId.$" = "States.Format('archibrief-review-session-{}', $.review_id)"
        }
        # ResultPath merges the task's Result under $.agentResult rather
        # than replacing state — same reasoning as every other Task fix
        # in this definition.
        ResultPath = "$.agentResult"
        # Added 2026-10-12 — closes part of Phase 6's "AgentCore
        # max-iteration/wall-clock/retrieval/token limits" gap
        # (Work-Project-Build-Plan.md). Without TimeoutSeconds, a Task
        # state's default is effectively unbounded (ASL's own default
        # ceiling, 99999999 seconds) — a hung Bedrock call or a stuck
        # AgentCore Runtime would hold this Standard-type execution open
        # indefinitely rather than failing visibly. 300s (5 minutes) is a
        # first-pass, deliberately generous ceiling given max_tokens=8192
        # and retrieval both already bound the call's real work — not
        # calibrated against a real execution's actual latency (no live
        # AgentCore+LangGraph execution exists yet to measure against),
        # so revisit once one does. Retrieval/token limits themselves are
        # the application-layer's job (max_tokens is already threaded
        # through runtime_entrypoint.py) — this only bounds the outer
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
      # Mirrors IngestRejected/IngestBlocked/ClarificationTimedOut's own
      # pattern: a bounded wait that's exceeded is a real, expected
      # terminal outcome, not a transient fault worth blind Retry.
      AgentInvocationTimedOut = {
        Type  = "Fail"
        Error = "AgentInvocationTimedOut"
        Cause = "InvokeAgent did not complete within 300 seconds — see this execution's history in CloudWatch for where the AgentCore Runtime invocation stalled."
      }
      # Fixed 2026-09-16 (Codex review, citing AWS's own direct
      # Step-Functions-to-Bedrock-Agent integration sample): the SDK
      # integration's response body lands at $.agentResult.Response
      # (capital R) as a raw JSON STRING, not at $.agentResult.response
      # (lowercase) or any nested .findings path — it must be parsed with
      # States.StringToJson before any field on it is reachable. ASL
      # doesn't allow chaining a further ".findings" property access onto
      # an intrinsic function's result in the same expression, so parsing
      # happens here in its own Pass state; AgentResponseGate and Validate
      # below both read from the resulting $.agentParsed.parsed object.
      # Still genuinely unverified against a real execution (no live
      # AgentCore+LangGraph+ZIP example exists to confirm the exact
      # envelope) — the first real CloudWatch execution history is the
      # authoritative check, same caveat as before.
      ParseAgentResponse = {
        Type = "Pass"
        Parameters = {
          "parsed.$" = "States.StringToJson($.agentResult.Response)"
        }
        ResultPath = "$.agentParsed"
        Next       = "AgentResponseGate"
      }
      # New state (2026-09-16 fix): runtime_entrypoint.py's invoke() can
      # return {"status": "needs_clarification", ...} with no "findings"
      # key at all (PreflightGate pausing for a required field) — before
      # this fix, InvokeAgent unconditionally went to Validate, whose
      # handler does event["findings"] directly and would KeyError.
      # needs_clarification is a real, expected, non-failure outcome per
      # runtime_entrypoint.py's own docstring, not an error to Fail on.
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
      # Replaced 2026-10-01 (was a bare Succeed — stopped the execution
      # permanently with no way to ever actually resume it once a human
      # answered). Pauses via the lambda:invoke.waitForTaskToken service
      # integration pattern: store_clarification_token.handler persists
      # the task token on the review's DynamoDB item and returns
      # immediately, but THIS STATE does not complete until something
      # else calls SendTaskSuccess/SendTaskFailure with that same token —
      # which only happens later, out-of-band, when clarify_review.handler
      # (behind POST /reviews/{reviewId}/clarify) receives a human's answer. Corrected design
      # per Work-Project-Build-Plan.md's 2026-09-17 entry: Codex originally
      # proposed `dynamodb:updateItem.waitForTaskToken`, independently
      # verified against AWS's own integration-pattern-support table as
      # NOT supported for DynamoDB (or Bedrock AgentCore) — only a small
      # number of services (notably Lambda, ECS, SQS, SNS, Glue,
      # SageMaker, EMR) support waitForTaskToken at all.
      #
      # TimeoutSeconds bounds how long a review can sit waiting on a human
      # — 7 days, chosen as a generous but non-infinite default (ASL's own
      # default would otherwise let this wait essentially forever). A
      # timed-out clarification is a legitimate terminal outcome, not a
      # transient fault worth Retrying.
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
            # Found 2026-10-12, live-tested: this Lambda previously read
            # os.environ["REVIEWS_TABLE_NAME"], never set anywhere — a
            # real KeyError the first time this branch (needs
            # clarification) was ever exercised live. Matches the same
            # literal-Parameter convention Audit/Finalize already use
            # for this exact value, below.
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
        Next = "PrepareAgentInputAfterClarification"
      }
      ClarificationTimedOut = {
        Type  = "Fail"
        Error = "ClarificationTimedOut"
        Cause = "No answer was submitted via POST /reviews/{reviewId}/clarify within the 7-day window."
      }
      # Rebuilds $.agentInput the same way PrepareAgentInput does, except
      # baseline_answers is folded through States.JsonMerge with
      # clarify_review.handler's SendTaskSuccess output
      # ({"baseline_answers": {...}}, landed at $.clarificationAnswer per
      # StoreClarificationToken's own ResultPath above) instead of being
      # copied straight from the original request. A separate state
      # (rather than adding a Choice inside PrepareAgentInput) because ASL
      # has no way to conditionally pick between a plain JSONPath copy and
      # an intrinsic-function merge for the same field within one
      # Parameters block.
      #
      # This can't be done as "$.baseline_answers.$" = JsonMerge(...) with
      # ResultPath "$.baseline_answers" on its own Pass state: ResultPath
      # replaces the path with whatever the Parameters object evaluates
      # to, and Parameters must itself be a JSON object literal — so that
      # approach would write {"baseline_answers": <merged>} AT
      # $.baseline_answers (double-nested), not <merged> itself. Folding
      # the merge into one of agentInput's own named fields sidesteps the
      # problem entirely, since agentInput's shape is static and known.
      #
      # Known, deliberately out-of-scope gap: (1) this does not update the
      # top-level $.baseline_answers, so Audit's own log of baseline_answers
      # later in this execution still reflects the pre-clarification
      # value, not the merged one — acceptable for now since Audit's
      # purpose is auditing the original request, not the agent's actual
      # input, but worth revisiting if that distinction matters later.
      # (2) if the agent asks for clarification again on this second pass
      # (the human's answer still didn't satisfy preflight_node), this
      # loops back through StoreClarificationToken with no cap on
      # repetitions. No evidence yet that this happens in practice;
      # revisit with a retry-count guard if it does.
      PrepareAgentInputAfterClarification = {
        Type = "Pass"
        Parameters = {
          "review_id.$" = "$.review_id"
          # clarification_note is always present on clarificationAnswer
          # (clarify_review.handler always returns it, "" when the user
          # left the notes box empty — see that handler's own comment)
          # — appended here because workload_brief is the only field
          # reason_node's prompt actually reads; baseline_answers itself
          # never reaches the model (added 2026-10-13, frontend
          # clarify-step.tsx's shared "anything else" box).
          "workload_brief.$"             = "States.Format('{}{}', $.workload_brief, $.clarificationAnswer.clarification_note)"
          "baseline_answers.$"           = "States.JsonMerge($.baseline_answers, $.clarificationAnswer.baseline_answers, false)"
          "retrieval_query.$"            = "$.retrieval_query"
          "rule_findings.$"              = "$.ruleEngineResult.findings"
          "deterministic_rule_version.$" = "$.ruleEngineResult.rule_version"
        }
        ResultPath = "$.agentInput"
        Next       = "RecordStageReasoning"
      }
      Validate = {
        Type     = "Task"
        Resource = aws_lambda_function.this["validate"].arn
        # Validate's handler (backend/lambdas/validate/handler.py) reads
        # event["findings"] directly — sourced from ParseAgentResponse's
        # parsed object above, now that its real field path (.Response,
        # parsed, capital-R) is confirmed rather than guessed.
        Parameters = {
          "findings.$" = "$.agentParsed.parsed.findings"
        }
        # Fixed 2026-09-16: Validate previously had no ResultPath either
        # — its return ({status, valid_findings, rejected_count,
        # rejected}) replaced state wholesale, same bare-replacement bug
        # as every other task in this chain before this pass.
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
      # Fixed 2026-09-16: backend/lambdas/audit/handler.py's
      # AuditLogEntry needs review_id (required) plus optional
      # baseline_answers/guardrails_decisions/deterministic_rule_version/
      # corpus_version/model_id (all read via event.get(...), so omitting
      # a key here is a safe no-op on the handler side, unlike omitting
      # one of the required-input-contract fields above). Sourced from
      # wherever each has actually accumulated in state so far:
      # review_id/baseline_answers from the original execution input,
      # guardrails_decisions from Ingest's own inline Guardrails check,
      # deterministic_rule_version from RuleEngine's rule_version output.
      # corpus_version and model_id have no equivalent source anywhere in
      # this state machine (runtime_entrypoint.py never returns either)
      # and are left absent rather than guessed.
      Audit = {
        Type     = "Task"
        Resource = aws_lambda_function.this["audit"].arn
        Parameters = {
          "review_id.$"                  = "$.review_id"
          "baseline_answers.$"           = "$.baseline_answers"
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
      # Fixed 2026-09-16: backend/lambdas/finalize/handler.py needs
      # event["review_id"] and event["findings"] (both required — bare
      # indexing) plus optional report_bucket/reviews_table_name.
      # Audit's own return ({"status": "recorded", "audit_id": ...})
      # carried neither review_id nor findings, so Finalize previously
      # received an incompatible event regardless of every upstream fix.
      # findings comes from Validate's valid_findings (the Finding-schema-
      # validated list, not the agent's raw unvalidated output) — matches
      # ADR-0022's layer 3/4 ordering (Validate gates what Audit/Finalize
      # ever see). report_bucket/reviews_table_name (fixed 2026-09-17):
      # plain literal Terraform values now, not "$.xxx" JSONPath — these
      # are infra constants known at apply time, never part of the
      # caller's request (see the required-input-contract comment above).
      # workload_brief added 2026-10-01: no DynamoDB item anywhere
      # persists the original brief, and deeper_review.handler (the "go
      # deeper" endpoint) needs it to re-invoke Reason later — the
      # evidence ledger in S3 is this project's source of truth for full
      # review content (ADR-0007/0042), so Finalize writes it there
      # rather than adding a new DynamoDB field.
      # preflight_fields/defaults_version also added 2026-10-01: found
      # while fixing get_review's response shape to actually match the
      # frontend's ReviewReport contract — runtime_entrypoint.py's invoke()
      # previously dropped preflight_fields on every path except the
      # needs_clarification early exit, so a COMPLETED review's baseline
      # answers (per-field answered/assumption/not-observable outcomes,
      # ADR-0031) were never persisted anywhere. $.agentParsed.parsed is
      # whichever InvokeAgent response actually completed the review — the
      # first one, or (after a needs_clarification round trip) the retry
      # following PrepareAgentInputAfterClarification — either way it's
      # the right, final preflight outcome to persist.
      Finalize = {
        Type     = "Task"
        Resource = aws_lambda_function.this["finalize"].arn
        Parameters = {
          "review_id.$"        = "$.review_id"
          "findings.$"         = "$.validateResult.valid_findings"
          "workload_brief.$"   = "$.workload_brief"
          "preflight_fields.$" = "$.agentParsed.parsed.preflight_fields"
          "defaults_version.$" = "$.agentParsed.parsed.defaults_version"
          # Added 2026-10-12 for a first-pass cost_estimate_tier heuristic
          # (backend/lambdas/finalize/handler.py's compute_cost_estimate_tier)
          # — safe to reference unconditionally: IngestResponseGate already
          # routes a "rejected"/"blocked" Ingest result to a Fail state
          # before RuleEngine/Finalize ever run, so $.ingestResult.resources
          # is guaranteed present by the time this Task executes.
          "resources.$"        = "$.ingestResult.resources"
          "report_bucket"      = var.reports_bucket_name
          "reviews_table_name" = var.reviews_table_name
        }
        End = true
      }
    }
  })

  tags = var.tags
}
