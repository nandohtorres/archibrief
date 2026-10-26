# Corrected evaluation criteria and local pipeline replay

The old scoring guide overclaimed what six Terraform configurations proved.
The versioned semantic oracle now distinguishes authentication from invocation
policy, rejected SQS mappings from runtime retry behavior, API methods from
backend integrations, AWS Backup selection from native RDS retention, bucket
names from replication, and explicit source retention from derived copy retention.
Primary AWS guidance was rechecked on 2026-10-23; links and detection owners are
in `tests/backend/adversarial/semantic_oracle.json`.

Eight supplemental tests establish those fixture premises and ensure missing
deterministic detections cannot become passes merely by attaching corrected
criteria. The frozen key/fixtures/saved results remain unchanged. Fresh exports
show historical probe adjudication separately from unscored semantic review.
Missing summary extraction is still a coverage gap, not closed by parser tests.

The free replay CLI composes existing production functions around the real
LangGraph: archive/parse, rules/resource summary/diagram, preflight, retrieval,
clarification screening, reasoning, citation and plain-language verification,
rule/model merging, schema validation, quality, ledger and report construction.
Only service responses are recorded; it constructs no SDK clients. It retains
raw/malformed responses and fails its contract gate for pauses, errors or
rejections. Nine real-graph tests cover clarification, screening, malformed
responses, rejected/partial batches, consistent review identity and fresh private
artifacts. This is free local contract replay, not deployed AWS integration or a
model-quality score. No production report-price/effort implementation changes.

The merged retrieval diagnostic now selects all 18 development and 14 holdout
queries by default, reports each set separately, includes failed attempts in
the hit-rate denominator, tests the downstream citation schema and metadata,
and records merged order and evidence bytes. `--sample` preserves the old partial
five-query diagnostic. An explicit optional hit-rate threshold is honored;
schema/empty-result failures always fail the command. Hash format is checked,
not source content; semantic support remains unmeasured. No ranking change was
made without measured evidence.

Reasoning artifacts retain raw and accepted findings. Whole-output phrase flags
include quotes, rejected and not-observable output instead of silently dropping
them. Contextual review is required for hits and the CLI exits nonzero, while
the semantic verdict stays unscored. Safe refutations are not automatically
called harmful. The historical quote-stripping diagnostic remains distinguishable.

Validation: final backend regression passed **1,178 tests**, with 5 skipped and
26 documented coverage gaps deselected. Ruff lint passed; all 123 checked Python
files are formatted. Both staged checkpoints passed Gitleaks. Frozen key SHA256
remains `577c434392ef0f4ea559098c3c18a4921c629d9fd3e7e0b582a9d7a455ee6fe9`;
fixtures, saved results and prepared historical inputs have no diff. The full
merged offline preview covers 32 queries and a 64-call upper bound without
constructing clients.
All evaluations here used local responses or offline previews. No AWS/model
evaluation, deployment, push or remote PR occurred.

Remaining P07/P08 work: stronger typed extraction assertions as P11–P16 land,
human semantic adjudication, full production paid evaluation and live integration,
source-content verification and the remaining evaluator counterexamples. Internal
monetary admission/version-manifest work remains P09; report money/effort redesign
is deferred by Fernando's instruction.
