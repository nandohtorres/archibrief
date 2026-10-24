# Configuration observations and bounded coverage

Continued the larger redesign after Fernando explicitly asked to keep working
until finished. This checkpoint implements a shared observation foundation and
supported slices for placement, routing, retention, backup selection and entry
paths. [Coverage](../terraform-coverage.md) records exact support and limits.

The parser keeps Region-only provider configuration and local singleton module
mapping; credentials are discarded. Observations preserve stable scoped resource
identity, inspected settings, explicit uncertainty, source module and versions.
They distinguish provider versus resource Regions, native versus AWS Backup
retention, inherited versus explicit copy retention, and names versus actual
replication/invocation relationships. Bounds and omissions are explicit.

Three deterministic additions detect fully known counted instances sharing one
AZ, invalid SQS timeout mappings and current-expiration-only versioned lifecycle
rules. Negative controls prevent claims from dynamic/conditional/unknown input.
Risk assessments and clear engineering recommendations add no new monetary or
effort recipes. Report/HTML/JSON scope metadata, chat context bounds and diagram
Region/AZ details use the same observations. Reason/chat prompts are versioned.

Local backend regression: **1,209 passed / 5 skipped / 26 coverage-gap cases
deselected**. Separately running all frozen coverage cases yielded **18 passed /
8 failed**, two modes per expectation. Four expectations remain: routing facts
exist but F04-D-07 requires a finding, and F07-D-03/D-04/D-05 require public access
or backend claims that the fixture does not establish. No unsupported claim was
added to satisfy them. Two other frozen lexical false positives have documented
typed supplemental contracts and counterexamples; raw verdicts stay visible.

Final focused backend checks: 76 passed, including three additional conservative
relationship controls after the full regression. Frontend: 83 unit tests passed;
lint/types passed; the scope-disclosure browser
test passed against locally built static variants. Final focused checks cover
the conservative relationship guards and public metadata. Ruff and staged
secret-scan results are recorded at save. No paid model calls, Terraform
execution, deployment or push occurred. The full backend wall time crossed a
suspended overnight session, so it is not a useful performance measurement.

Frozen key, fixtures, historical saved results and model input snapshots remain
unchanged. No report price, effort, cost aggregation or recipe values changed.
Before release, rebuild Ingest/RuleEngine and other affected Lambdas plus the
AgentCore runtime, deploy the compatible API/UI and validate the live flow
separately. Unsupported slices remain explicit; no complete Terraform interpreter
or deployed-account guarantee is claimed.
