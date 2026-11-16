# ADR-0063: bounded finding-verification experiment

> **Combined-candidate checkpoint (2026-11-16):** This preview is included with admission/cost checks and rejected-claim disclosure, default OFF. Request compaction keeps claim fields, mentioned resources plus one reference step, and cited passages within the unchanged 86 KiB bound. Contradiction can be established by supplied facts or evidence; supported cited detections still require their passage. Failed checks keep findings unchecked. See [current status](../current-status.md) for the current protocol and evaluation/release gates. The earlier implementation snapshot below preserves its original version label.

Status: implemented locally as a default-off preview, not accepted for enabled
production use. No live evaluation authorized. See pilot P3b and the launch
notes' paid-evaluation proposal.

After deterministic citation/shape/remediation checks, batch at most 12 surviving
model findings into one additional forced-tool response. Use only pinned input
facts, declared requirements and retrieved passages. Candidate text is untrusted
data. No tools, retrieval changes, new findings, rewritten fixes or corrective
loops. Rule findings are unchanged.

Owner decision A (2026-11-16): fail open on verification failure. Timeout,
throttle, malformed/partial output, candidate limit, failed citation integrity or
exhausted budget keeps the original findings, labels them Not independently
checked and records incomplete status. No failure-based suppression.

Validate each verdict independently against existing finding/fact/evidence IDs.
Missing, duplicate, malformed or unsupported verdicts leave only their own finding
unchecked; valid sibling verdicts still apply. Contradicted detections are removed.
A supported detection with an unsafe/unworkable fix is retained and both technical
and plain actions receive a neutral confirmation line. Citationless not-observable
candidates do not require evidence IDs. Log suppressed/unchecked concern/category
and bounded IDs, never finding text. The shared replay/production protocol is
finding-verification@2026-11-16-preview2. Agreement is not a semantic guarantee.

The experimental initial-review generator is capped at 8192 output tokens;
verifier at 4096. The same GenerationBudget object reserves both calls within
the existing <=$0.40 operation receipt and deadline, with no refund of unknown
usage, no retry and no third call. Ordinary mode still permits one generation
call; deeper mode never enables the verifier. P3b adds no infrastructure or IAM
settings in this implementation. Server environment ARCHIBRIEF_VERIFY_FINDINGS
must literally be true to opt in; it is absent/off by default and cannot be set
by a submitted payload. Do not enable before cost/token admission validation,
paired controls, kill-switch/failure checks and owner rollout approval.

Log only counts, version and usage, distinguishing verification from generation.
Aggregate token/time/cost includes both phases; unknown verifier usage cannot be
reported as the cheaper generator-only total. Quality reasons say additional
verification checks, never verified correct. Persist preview version metadata
with internal quality data. Public summaries disclose incomplete suppression.

Citation integrity checks compare exact text and hashes/metadata; semantic support
is separate. Offline checks of the saved 43 citations establish reproduction,
while manual relevance review identifies related-but-insufficient and unrelated
sources. No historical score/oracle is silently rewritten.

Accuracy-only rule/input/remediation repairs are separately releasable without
P2 or P3b. The experiment stays in integration until justified by evaluation.
