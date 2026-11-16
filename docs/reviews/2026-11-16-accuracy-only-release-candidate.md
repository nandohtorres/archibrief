# Accuracy repairs without P2: handoff to Claude

Worktree: `../archibrief-accuracy-release`; branch `release/accuracy-repairs`;
base `8c90443a6904eb73815f022e6f6674df11b61dba` (released PR 67).
All changes remain uncommitted. No push, PR, merge, paid calls or deployment.
New files are untracked: use `git status --short` as well as `git diff HEAD`.

## Scope

This isolates reviewed rule/input/remediation repairs from integration. No P2
admission, CountTokens, budget client, runtime/worker wiring, infrastructure,
IAM or P3b changes. No new model generation call. Existing output cap is unchanged;
additional structured facts can change input cost, so do not promise identical
cost or a new accuracy score without the proposed evaluation.

- Correct DLQ retention: source plus one-day inspection allowance, with a
  different preservation/retry process if SQS's 14-day limit cannot fit it.
  Stakeholder card uses matching new-rule wording.
- Accurate backup wording for missing, zero, positive and unresolved values;
  fallback concern inference understands old and new titles. Default is labelled
  AWS's default, not the provider's.
- IAM wildcard findings state declared policy breadth and relevant policy limits;
  input facts expose boundary intersection, scoped resources, KMS consumers and
  actual Lambda invocation paths.
- Reject unsafe Object Lock, boundary-reversal, KMS removal and wrong Lambda DLQ
  advice. Preserve negated/cautionary counterexamples and correctly targeted
  sibling findings. Model DLQ advice yields to the authoritative rule.
- Retain the retired EBS capacity finding with an explicitly labelled safe action
  correction instead of losing the useful warning to unsafe shrink wording.
- Discard invalid optional plain blocks before applying remediation checks.
- Preserve released theme and mobile fixes; only DLQ card copy changes frontend.

Versions: rule_engine@2026-11-15b; remediation_checks@2026-11-15b;
reason_prompt@2026-11-15-facts. Prompt prose/schema and chat prompt unchanged.

## Independent local validation

- Full backend: **1772 passed, 13 skipped, eight coverage-gap cases deselected**.
  Four corpus checks skip in this fresh worktree; nine require TRIVY_PATH.
- Frontend: **130 passed**, typecheck/lint/format clean.
- Packaging/transitive-import and runtime-no-ingestion-dependency checks:
  **26 passed**. Backend Ruff lint/format clean.
- Known-output replay on equivalent integration repairs rejects nine problematic
  model findings and corrects one EBS action, without development keyword coverage
  loss; this is not fresh generation or semantic accuracy measurement.
- After final AWS-default wording correction: **63 affected accuracy tests passed**;
  no logic change. Diff whitespace check clean.

Shared catalog changes are packaged into **get_review, rule_engine, scan,
finalize, deeper_review, ask_question, list_questions and validate** (scan changes
through trivy_checks; other listed functions may only carry catalog). AgentCore
runtime also changes through reason.py and shared recommendation/catalog modules.
This is not a four-Lambda-only release. Deeper worker may use the same deeper ZIP;
derive actual resource impact from the final Terraform plan.

## Claude's next part

Review full diff and every new file; confirm no P2/P3b dependencies. Build all
affected packages/runtime with existing pinned tools; inspect source hashes,
native dependencies and actual Terraform resource changes. This offline handoff
does not claim production ZIP builds, a Linux cold start, hosted CI or plan/apply.

Commit/push, PR/CI, merge and deployment still need the owner's approvals.
Successful master CI automatically deploys frontend with no required-reviewer
gate: preserve the approved backend-first rollout before allowing that merge,
or obtain an explicitly approved hold. Do not silently change automation.

Treat this as targeted known repairs, not completion of accuracy release gates.
Semantic citation grounding, P3b effectiveness and fresh holdout results remain.
Evaluation proposal and manual citation review live in archibrief-launch.
