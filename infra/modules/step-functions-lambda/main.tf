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
  lambda_specs = {
    ingest      = { handler = "backend.lambdas.ingest.handler.handler", zip = var.lambda_zip_paths.ingest }
    rule_engine = { handler = "backend.lambdas.rule_engine.handler.handler", zip = var.lambda_zip_paths.rule_engine }
    validate    = { handler = "backend.lambdas.validate.handler.handler", zip = var.lambda_zip_paths.validate }
    audit       = { handler = "backend.lambdas.audit.handler.handler", zip = var.lambda_zip_paths.audit }
    finalize    = { handler = "backend.lambdas.finalize.handler.handler", zip = var.lambda_zip_paths.finalize }
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

resource "aws_lambda_function" "this" {
  for_each      = local.lambda_specs
  function_name = "${var.name_prefix}-${each.key}"
  role          = aws_iam_role.lambda[each.key].arn
  handler       = each.value.handler
  runtime       = "python3.12"
  filename      = each.value.zip
  source_code_hash = fileexists(each.value.zip) ? filebase64sha256(each.value.zip) : null

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  # Only Ingest calls Guardrails directly (ADR-0033) — Reason's own call
  # happens inside AgentCore Runtime, not this Lambda, and reads the same
  # deployed Guardrail by ID/version through its own config path.
  dynamic "environment" {
    for_each = each.key == "ingest" ? [1] : []
    content {
      variables = {
        GUARDRAIL_ID      = var.guardrail_id
        GUARDRAIL_VERSION = var.guardrail_version
      }
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
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [var.reviews_table_arn]
  }

  dynamic "statement" {
    for_each = var.agentcore_runtime_arn == null ? [] : [1]
    content {
      effect    = "Allow"
      actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
      resources = [var.agentcore_runtime_arn]
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
#     "archive_path": "...",        # Ingest
#     "workload_brief": "...",      # Ingest, then re-used by InvokeAgent
#     "dest_dir": "...",            # optional for Ingest (has its own default)
#     "retrieval_query": "...",     # InvokeAgent -> runtime_entrypoint.invoke()
#     "baseline_answers": {}        # InvokeAgent + Audit (pass {} if none)
#   }
# report_bucket/reviews_table_name are DELIBERATELY NOT part of this
# contract (removed 2026-09-17, see Work-Project-Issues-Log.md) — they're
# Terraform-known infra constants (var.reports_bucket_name/
# reviews_table_name), not caller-supplied input; requiring the client to
# know real internal AWS resource names was a real bug, not a design
# choice. audit_table_name is deliberately NOT required here either —
# Audit's Parameters below omit it entirely (not merely leaving it null)
# so event.get(...) on the Lambda side stays a genuine "skip the write"
# no-op rather than a state-machine-level path error, matching this
# account's still-pending DynamoDB table bootstrap.
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
        Default = "Ingest"
      }
      KillSwitchActive = {
        Type  = "Fail"
        Error = "KillSwitchActive"
        Cause = "ADR-0030 application kill switch is set to true — no new paid work starts until it's reset."
      }
      # Fixed 2026-09-16 (Codex review, re-verified directly against
      # backend/lambdas/ingest/handler.py): Ingest's raw return
      # ({status, resources, variables, files_parsed, not_observable,
      # workload_brief, guardrails_decisions}) used to REPLACE state
      # entirely (no ResultPath) — losing review_id and everything else
      # the original execution input carried before RuleEngine even ran.
      # ResultPath merges it under $.ingestResult instead, alongside the
      # untouched original input.
      Ingest = {
        Type       = "Task"
        Resource   = aws_lambda_function.this["ingest"].arn
        ResultPath = "$.ingestResult"
        Next       = "RuleEngine"
        # NOT HANDLED, flagged deliberately rather than silently ignored
        # (2026-09-16): if Ingest returns status "rejected" or "blocked"
        # (IngestRejected / a Guardrails block), $.ingestResult has no
        # "resources" key and RuleEngine's parsed.get("resources", {})
        # below just silently produces zero findings rather than halting
        # the execution with a clear reason. Out of scope for this pass
        # (not one of the enumerated fixes) — a Choice state gating on
        # $.ingestResult.status the same way AgentResponseGate below
        # gates on the agent's status is the natural follow-up.
      }
      # RuleEngine's handler reads event["parsed"] and event["review_id"]
      # directly (backend/lambdas/rule_engine/handler.py) — neither name
      # exists at top level once Ingest's output moved to $.ingestResult
      # above. Parameters rebuilds RuleEngine's input explicitly: the
      # whole $.ingestResult dict already has the "resources"/"variables"
      # shape rule_engine.py's _resources() helper expects under the key
      # "parsed", so it's aliased wholesale rather than field-by-field.
      RuleEngine = {
        Type = "Task"
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
          "review_id.$"                   = "$.review_id"
          "workload_brief.$"               = "$.workload_brief"
          "baseline_answers.$"             = "$.baseline_answers"
          "retrieval_query.$"              = "$.retrieval_query"
          "rule_findings.$"                = "$.ruleEngineResult.findings"
          "deterministic_rule_version.$"   = "$.ruleEngineResult.rule_version"
        }
        ResultPath = "$.agentInput"
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
        Next       = "ParseAgentResponse"
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
            Next         = "NeedsClarification"
          }
        ]
        Default = "Validate"
      }
      # Succeeds the execution as-is (with $.agentParsed.parsed carrying
      # needs_clarification/preflight_fields as the last thing written) —
      # deliberately NOT a Fail state, matching runtime_entrypoint.py's
      # own framing of this as a legitimate stop, not an error Step
      # Functions' Catch/Retry machinery should react to.
      NeedsClarification = {
        Type = "Succeed"
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
        Type = "Task"
        Resource = aws_lambda_function.this["audit"].arn
        Parameters = {
          "review_id.$"                 = "$.review_id"
          "baseline_answers.$"           = "$.baseline_answers"
          "guardrails_decisions.$"       = "$.ingestResult.guardrails_decisions"
          "deterministic_rule_version.$" = "$.ruleEngineResult.rule_version"
        }
        ResultPath = "$.auditResult"
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
      Finalize = {
        Type = "Task"
        Resource = aws_lambda_function.this["finalize"].arn
        Parameters = {
          "review_id.$"         = "$.review_id"
          "findings.$"          = "$.validateResult.valid_findings"
          "report_bucket"       = var.reports_bucket_name
          "reviews_table_name"  = var.reviews_table_name
        }
        End = true
      }
    }
  })

  tags = var.tags
}
