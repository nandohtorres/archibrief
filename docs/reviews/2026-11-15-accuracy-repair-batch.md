# Accuracy repair batch alongside P2

> **Critique fixes (revision b):** omitted-backup wording and new-title lookup are
> fixed; Lambda checks no longer judge an unbound subject using other functions;
> creation-only checks require Object Lock as the actual subject. T2-08 is
> retained with a visible fixed safety correction, preserving detection, evidence
> and citation. Updated replay rejects nine problem findings, corrects one and
> shows no development keyword-coverage regressions. The earlier Medium loss
> described below belongs to the first revision.
>
> Tags: `rule_engine@2026-11-15b`, `remediation_checks@2026-11-15b`.
> Prompt prose/schema and catalog recipes/tiers remain unchanged; only concern
> lookup adds compatibility for the new backup titles.

Revision b's EBS correction is limited to capacity/retirement findings whose only
actionable failure is in-place shrinking. Both actions receive an explicit
"ArchiBrief safety correction" with conditional dependency/recovery checks and
supported migration guidance. Unsupported core claims, mixed failures and other
defects still fail closed. No evidence, citation or assessment is rewritten.

Local candidate only. No model calls, AWS configuration changes, commits, pushes
or deployment. Claude's Stakeholder Brief worktree was not edited.

## Changes

- `rule_engine@2026-11-15`: standard-queue DLQ advice recommends 14 days and states
  the source-age plus one-day inspection allowance explicitly (432,000 seconds
  for the current four-day source). When that allowance exceeds SQS's maximum,
  the rule calls for a different handling plan instead of an impossible setting.
- Trivy backup wording reports the resolved value: disabled at zero, the actual
  positive window, or an unresolved scanner observation. It no longer substitutes
  "unset or 1" for a declared zero or assumes no other recovery source exists.
- Wildcard identity policies are no longer labelled effective "full admin".
  Attached boundaries are identified as parsed/unresolved; boundary presence alone
  never reduces severity or certifies narrow effective access.
- New bounded relationship facts show direct/alias-mediated KMS references,
  boundary actions/resources when parseable, and known URL/polled/SNS invocation
  paths. Empty consumer lists never prove a key unused. External usage and
  unsupported references/invokers remain unestablished. Omissions are counted.
- `remediation_checks@2026-11-15` rejects known unsupported EBS shrinking,
  Object Lock replacement/creation-only claims, unscoped compliance-mode advice,
  boundary intersection reversals, unverified key removal/contradicted unused
  claims and function-level DLQ fixes lacking a supported asynchronous path.
- A deterministic DLQ rule owns that same queue's retention recommendation;
  duplicate model minima are suppressed. Its original rule finding remains.
  The check also runs against a deterministic DLQ parent during deeper review.
- Both technical and retained plain-language actions are checked. Invalid plain
  blocks still get dropped without suppressing a safe core. Rejection categories
  and a remediation-policy version are logged without finding text.
- Lambda package sources include the new relationship module. The AgentCore
  runtime does not gain an ingestion/HCL-parser dependency.

The prompt prose/tool schema did not change. Model input provenance is now
`reason_prompt@2026-11-15-facts` because new structured facts are supplied. This
is a new generator-input revision, not a same-version repeat of the P1 baseline.

## Validation and limits

Full backend suite after the primary changes: **1,827 passed, 9 skipped, 8 known
coverage-gap cases deselected**. Final focused checks after additional counterexamples
and plain-block handling: **103 passed**. Backend Ruff formatting/lint and package
import checks pass. No frontend or integrated Stakeholder Brief tests claimed.

The offline saved-output diagnostic is reproducible with:

```powershell
.\backend\.venv\Scripts\python.exe scripts/check_accuracy_candidate.py --output backend/build/evaluations/p1/accuracy-candidate-replay-2026-11-15.json
```

It parses/scans the synthetic fixtures locally, reconstructs model inputs with
historical passages, and checks already-published findings against current gates.
No generation, embeddings, vector retrieval, Guardrails or CountTokens calls.
The recorded ledgers, oracles and corpus are not changed.

The first replay excludes the ten previously judged remediation-problem findings:
the three harmful ones, four insufficient DLQ minima, two inapplicable Lambda
failure-path fixes and the EBS impossible alternative. This is filter applicability
on known examples, **not measured improvement on new generation**. The rule fixes
also address backup text and the effective-admin label.

**Known regression:** slot 10 loses the valid Medium `T2-08` scratch-volume issue
when its mixed good/bad finding is rejected as a whole. Do not hide this in an
average or present filtering as costless. Recovering safe advice for that issue
needs explicit treatment/evaluation; the guard does not silently rewrite it.
Development cases show no Critical/High keyword-coverage regressions. T3b is not
in that legacy matcher, so its automatic coverage diagnostic is null, not a pass.

All six current candidate inputs fit both exact and pre-retrieval byte bounds
with the historical evidence passages. Conservative bounds are 85,988; 84,751;
82,037; 82,360; 82,037; 82,360 bytes versus 88,064. This does not establish token
cost acceptance, current live retrieval size or latency. Free CountTokens remains
blocked on the previously approved administrator permission update.

The text checks are narrow regression guards. They are not a full IAM evaluator,
an exhaustive key-consumer/invoker extractor, citation entailment verification or
a proof that remaining recommendations are safe. In particular: boundary severity
calibration, subnet-name inference, unsupported observability assertions, fresh
held-out evaluation and P3b remain unfinished. No extra paid pass is enabled.

## Integration handoff

Claude's completed brief was captured separately at
`backend/build/integration-snapshots/stakeholder-complete-2026-11-15/`:
51 changed files, including 17 untracked and 3 deletions. Source status, diff,
HEAD and bytes verified unchanged during capture; its worktree remains intact.
A refreshed main capture and combined tests supersede individual-source test
results for integration readiness.

Main checkout also contains the uncommitted P2 and evaluation-runner work. Preserve
it all. New files for this batch include `resource_relationships.py`, the two
accuracy regression test modules, `check_accuracy_candidate.py` and this note.
An ordinary diff omits untracked files.

Likely conflicts beyond Claude's original table: `scripts/package_lambdas.py`
(union dependencies) and any test/provenance expectations importing current
`PROMPT_VERSION` or `RULE_VERSION`. Core facts/checks live outside Claude's
presentation/chat files. Keep the accepted concern IDs and catalog unchanged.
Do not copy entire directories over one another or claim separate suites validate
the combined candidate. Integrate only after Claude supplies a stable handoff.

AWS sources checked during implementation:
[SQS retention](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/setting-up-dead-letter-queue-retention.html),
[existing-bucket Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html),
[EBS size limitations](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html),
[boundary semantics](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html),
[asynchronous failure handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html),
[SNS invocation](https://docs.aws.amazon.com/lambda/latest/dg/with-sns.html),
[SQS polling](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html).
