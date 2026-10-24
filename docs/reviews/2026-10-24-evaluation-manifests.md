# Evaluation reproducibility and generation admission

All six CLI previews and attempt journals now share a start-of-run
manifest. It fingerprints working source, selected cases, frozen fixtures,
rubric, schema, prompts, local corpus and dependency locks, and records installed
Python/package versions plus resolved model/Region/index/guard configuration.
Missing local data, unreadable files and unverified live index state are explicit.
No SDK client or shell command is needed to build it. Raw cases/source content,
credentials and arbitrary environment variables are not published in the manifest.

An aggregate generation-output ceiling is checked against selected scope before
any clients are constructed. Each dispatched model request reserves its requested
maximum; a failed request never refunds it. Runtime metering stops the next call
when it cannot fit. UTC attempt timestamps, known usage and bounded retrieval
identity remain available even if subsequent parsing fails. Actual source text,
URLs and prompts are absent from call journals; full model artifacts stay private.

This is not verified monetary admission, total input-token accounting or a hard
in-flight cancellation. Prices were not invented. No report money/effort or
aggregation implementation changed. Actual paid runs still require their own
approved scope and configuration. Contextual semantic grading and deployed AWS
integration remain separate from source fingerprints.

Validation includes no-client previews for every runner, changed-code/case hashes,
secret canaries, missing corpus disclosure, real schema/prompt identification,
retrieval identity bounds and failed-generation reservation. Final results are
recorded in the release-readiness handoff. No paid run, push or deployment occurred.

The sixth runner reuses free replay's real graph/report/audit assembly with
metered SDK adapters. Required baselines, fresh private output, call/output caps
and confirmation are checked before clients. Ingest/reason input screens are
counted separately. Every scheduled case is written before work and updated
atomically. A fake SDK regression proves one model failure cannot erase the next
case or its report; no live persistence or model quality is implied.
