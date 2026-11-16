# P2 pilot request admission

Policy: `review-request-budget@2026-11-16`. Implemented locally; **release validation
is incomplete**. No infrastructure was applied and no generation evaluation was
run as part of this implementation.

## Limits and enforcement

| Limit | Initial review | Deeper review |
| --- | ---: | ---: |
| Complete canonical request, UTF-8 bytes | 88,064 | 88,064 |
| Evidence contribution, including outer JSON escaping | 43,008 | 20,480 |
| Output tokens | 12,288 | 4,096 |
| Maximum stored operation reservation, micro-USD | 400,000 | 200,000 |
| Reserved allowance for other paid operations, micro-USD | 20,000 | 10,000 |
| Generation dispatches | 1 | 1 |
| Shared analysis dispatch window | <=400 seconds | <=240 seconds |

The complete request includes model ID, system text, user content, tool schema,
tool choice and inference configuration. It is canonical application JSON, not
SDK HTTP wire bytes. Caller-provided token limits cannot increase the runtime
limits. This version supports `us.anthropic.claude-sonnet-4-6` only.

1. Ingest parses and inventories without Bedrock access. Reject unknown roots,
   unusable inventories or more than 50 known declarations before paid work.
2. A trusted worker binds the exact runtime payload, archive, input and inventory
   to the existing reserved operation row. No caller-supplied admission is trusted.
3. Before paid screening/retrieval, assemble the complete fixed request with empty
   evidence. Require fixed bytes plus the maximum evidence allowance <=88,064.
   Use unbilled CountTokens on the fixed system/messages/tool schema. Estimate an
   upper input allowance as that count plus evidence bytes plus 64 boundary tokens.
   Reserve maximum output plus other paid operations against the stored receipt.
4. Store the versioned envelope and deadline on that operation. Atomically claim
   its input screen once; ambiguous screening is never retried or refunded.
5. Runtime consistently checks own storage, exact payload binding, live scope,
   allowed input screen, budget version and deadline. Direct real Retrieve/Reason
   adapters require the same trusted context and generation budget.
6. Retrieve checks the shared deadline before each embedding/vector dispatch.
   Retain whole chunks within the evidence allowance, preserving citation text;
   disclose omitted chunks through `evidence_budget_limited` in the report/export.
7. Immediately before generation, measure the exact assembled request and call
   CountTokens again on all system/messages/tools. Reject unknown counts, excess
   bytes, excess maximum-output cost or an expired deadline. Reserve the entire
   possible generation cost before one dispatch. SDK retries are disabled and its
   read timeout uses the remaining analysis window.

The worker recalculates its available runtime wait after screening so finalization
time remains reserved. An already dispatched call can finish after the deadline
and still bill. Deadline checks prevent subsequent dispatch, not cancellation.

## Accounting and failure behavior

Generation estimates use the repository's US Sonnet 4.6 rates: 3.3 micro-USD/input
token and 16.5 micro-USD/output token, rounded upward. No prompt caching is
requested. These rates and the auxiliary allowances are policy assumptions;
validate pricing and service-specific auxiliary usage before claiming a hard
operational cost cap. They are not a whole-account AWS invoice guarantee.

The pre-retrieval byte bound is deterministic. One token per escaped evidence byte
plus boundary slack is a conservative planning estimate, not a proven tokenizer
bound. The final exact CountTokens gate independently enforces the generation
reservation; it cannot undo earlier screening/retrieval charges. CountTokens
failures stop dispatch, with no fallback estimate enabling generation.

Declaration/root and pre-screen envelope rejection make no paid Bedrock call.
The initial reservation is released only when failure is known to precede paid
work. Later or ambiguous failures retain reservations. Deeper failures retain
their reservation conservatively; this can overcount unused spend. Existing
day/month/visitor/review counters and kill switch remain authoritative.

A final generation-budget rejection publishes initial deterministic findings with
an explicit budget-limited quality notice and `model_outcome=not_invoked`.
Earlier screening/retrieval may have billed. A deeper rejection fails that job,
preserving the original report. Admission failures are explicit failures, not a
successful empty review. Existing cached deeper findings remain readable before
new-work eligibility checks; unusable legacy scope requires a fresh review.

## Evidence and remaining release checks

`scripts/check_p2_request_budget.py` runs offline by default. It reconstructs
current-code P1 slots 6/8/9/10/11/12 from local ledgers and corpus chunks. It
requires ordered retrieval IDs to agree across findings, citation content hashes
to match local chunks, and reconstructed user-content length to match logged
length. Complete sizes are 68,485; 79,589; 71,706; 72,704; 71,706; 72,704 bytes.
Evidence contribution ranges from 27,111 to 38,731 bytes. All six fit these byte
limits, including the full conservative fixed-plus-evidence byte allowance.

The proposed byte limits use nearest-rank p95 plus 10%, rounded upward to 1 KiB.
This is a six-run reconstruction, with repeated workloads, unsafe model outputs
and no original complete-request hash. It establishes neither high-quality
baseline acceptance nor latency/citation accuracy. Treat the limits as a tested
implementation candidate pending the release checks below, rather than implying
the original high-quality-baseline selection requirement has been fulfilled.

- Validate CountTokens support/permissions and full/fixed token counts on the
  reconstructed synthetic requests. Optional script flag `--count-tokens` sends
  their fixture inputs and AWS documentation to Bedrock; it never invokes
  generation, embeddings or Guardrails. The owner approved the free transfer;
  the first attempt stopped with `AccessDeniedException`, with one CountTokens
  attempt and zero paid calls. The profile assumes the Identity Center
  `ArchiBriefDeploy` role. The owner also approved the scoped permission update,
  but the only configured profile cannot administer Identity Center (`ListInstances`
  denied in us-east-2). An administrator must apply the prepared addition.
- Measure conservative-envelope false rejections, including bounded large IAM
  inputs, against accepted baseline and fresh held-out cases. Byte acceptance of
  six reconstructed requests does not establish cost acceptance.
- Validate auxiliary pricing/usage bounds and latency before representing the
  reserved amounts as a service-wide paid-operation ceiling.
- Review the deployment diff, build artifacts, run hosted CI and authorize a
  coordinated IAM/worker/runtime/frontend rollout. Nothing here auto-deploys.

The previously identified accuracy errors and P3b verification remain separate
release gates. These safeguards do not establish remediation correctness.

## Free-count permission prerequisite

The deployment-policy example now includes `BedrockReviewTokenCounts`: only
`bedrock:CountTokens` on the Sonnet 4.6 foundation model and US inference profile
in us-east-1. Substitute the real account ID for the example's placeholder.
It adds no generation, Guardrails or embedding action. For the SSO deployment
profile, an administrator must add this statement to the **ArchiBriefDeploy
Identity Center permission set** and provision that permission set to its existing
account assignment. Do not edit the generated `AWSReservedSSO_*` role directly
or replace its entire policy with the repository example.

This addition is approved but could not be applied with the available profile.
No live permission was changed; no alternate
credentials were used to bypass the denial. Re-run the approved free-count script
after the scoped permission update, then check cost and false-rejection results.

AWS references: [CountTokens overview](https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html),
[API input contract](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CountTokens.html),
[Sonnet 4.6 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html).


## Combined-candidate token-count compatibility (2026-11-16)

The cost gate is in the worker before paid screening/retrieval, then repeats on
the complete generation request immediately before dispatch. CountTokens now
uses foundation model ID `anthropic.claude-sonnet-4-6`; generation still uses
`us.anthropic.claude-sonnet-4-6`. System/messages/tool schema are identical to
those passed for generation. The request policy version is bumped so a stale
preflight envelope is not treated as admission under the new counter target.
Missing counts, malformed counts or an unaffordable conservative bound block
paid work and release an unspent receipt. Tests use fake counters and SDK-shape
contracts; real free-count acceptance and effective IAM still need release validation.

The required action for the free validation identity is `bedrock:CountTokens` on
`arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6`.
Retain existing inference permissions; this is not permission to generate.
The candidate's Terraform already grants the count action to initial/deeper
workers and AgentCore and allows it in their permissions boundary. An Identity
Center permission-set update for the deployment profile is a separate administrator
step, not a substitute for those runtime-role policies. No permissions were
changed live by this build.

The [CountTokens API contract](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CountTokens.html)
specifies a foundation model identifier; the
[Sonnet 4.6 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html)
marks token counting supported. This correction follows that documented target;
it does not claim a successful real call or that IAM was the only previous failure.
