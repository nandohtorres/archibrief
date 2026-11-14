# P1 small-workload corpus — draft, 2026-11-13

Source baseline: ArchiBrief `master` at `1e8ffb8`. Branch: `test/p1-corpus`.
No model output was consulted. No AWS API, scanner, paid review, Terraform init,
plan, apply, provider download, or infrastructure mutation was performed.

## Cases and allocation

There are **six Terraform roots and seven review cases**. T3b's two briefs use
the exact same Terraform files and oracle. The newer P0 contract section 10
supersedes the older 18-run table in the pilot plan section 4.

| Case | Root | Known declarations | Split | Planned runs |
| --- | --- | ---: | --- | ---: |
| T1-small | T1-small | 25 | development | 1 |
| T1-full | T1-full | 50 | development | 3 |
| T2-small | T2-small | 25 | development | 1 |
| T2-full | T2-full | 50 | development | 3 |
| T3a | T3a | 50 | development | 2 |
| T3b-neutral | T3b | 50 known, partial | held out | 1 |
| T3b-hostile | T3b | 50 known, partial | held out | 1 |

This describes 12 future reviews with $4.80 reserved at $0.40 each, **not
authorization to run them**. Run every case once, then T3a's repeat, then the
T1-full/T2-full repeats. Failures consume their slots; do not replace automatically.

T1 is a contractor access/export workload covering IAM, public management,
metadata access and an alternate Lambda URL. T2 is a records platform covering
database recovery, AZ resilience, evidence retention, queue failures and cost.
T3a combines those concerns with route-specific API authorization and a conflicting
EU/US provider placement. T3b is a queue-driven partner exchange with reused local
lanes, a late broad grant in a 12-statement IAM policy, bounded IAM permissions,
and missing remote-module evidence. T3b remains held out for both brief variants.

T1/T2 `main.tf` is byte-identical between the small and full versions. The full
versions add five named reporting/export archives, each with five declarations:
bucket, public-access block, versioning, lifecycle and transport-deny policy.
These are business-purpose extensions, not different planted defects. Paired
versions have identical core issue IDs, evidence and remediation. Report results
by size; do not treat duplicated issue families as independent statistical samples.

## What to submit and what to keep private

`manifest.json` identifies each case's exact Terraform file allowlist, brief,
oracle, split and run allocation. Archive **only** `terraform_files`, preserving
paths relative to the specified root so its `main.tf` is at the archive top.
Send only the selected brief as workload context, separately from the archive.

**Never upload `oracle.json`, `inventory.json`, the manifest, validation artifacts,
this README, or the other brief.** Do not tar an entire case directory wholesale.
The uncalled `T3b/modules/unused/main.tf` is intentionally part of the Terraform
input. It must be parsed safely but not counted as a reached declaration.

Inputs contain fictional account IDs, AMIs, image digests and external integration
identifiers. They are HCL/static-review fixtures, not deployable service packages.
Application artifacts, external identity providers and central alert subscriptions
are not supplied. No claim follows about their runtime existence or availability.

## Counting and independent validation

`inventory.json` in each root lists every reached resource identity, source file,
header line and instance multiplicity. It is produced by a separate simple HCL
walker, not derived from ingest's `known_y`. The validator compares both inventories
as full address sets and checks ingest's pending scope with `validate_scope`.
Modules, data blocks, variables, providers, IAM statements and ingress blocks are
not declarations. Resource-level `count=0` still contributes one declaration.

T3b has 20 root declarations plus 15 in `module.intake` and 15 in
`module.fulfillment`, although those two calls share one source directory. It has:

- One count-zero AWS declaration: `aws_security_group.legacy_console`.
- Two counted non-AWS declarations: `random_id.exchange` and
  `terraform_data.deployment_marker`.
- 47 active AWS declarations before any summary or detail omissions; this is
  **not X and not a claim that a model reviewed them**.
- One unreadable remote module: `module.archive_bridge` (`remote_source`).
- One disabled remote call with no child declarations or gap: `disabled_bridge`.
- One uncalled source resource, excluded from Y.

Ingest reports `known_y=50` and `count_complete=true` for the enumerated known
inventory. The remote-module gap still makes the complete workload total unknown.
Do not equate `count_complete` with complete review coverage.

Run from the worktree root using the existing backend environment:

```powershell
& '../archibrief/backend/.venv/Scripts/python.exe' -B tests/backend/fixtures/small_workloads/validate_corpus.py
```

In another checkout, use its Python environment with the backend dependencies.
The validator is read-only and blocks network connections, DNS and subprocesses.
It calls `parse_terraform_files` directly, never the handler or an SDK client.
It verifies file hashes, case allocation, splits, input allowlists, exact counts,
module attribution/multiplicity, source evidence lines/quotes, required oracle
fields, paired core equality, and the shared factual prefix of T3b's briefs.
`validation.json` records the local result and dependency/source fingerprints.

These checks do not substitute for Terraform provider-schema validation or prove
AWS deployability. They also do not establish findings recall, precision, cost,
latency, diagram correctness or safe model remediation. Those remain unmeasured.

## Oracle use and review

Every issue has an ID, one canonical resource address, severity, explicit
`must_find`, source/brief evidence, expected meaning, severity reasoning and safe
remediation. Critical/High issues are must-find. Safe counterexamples prohibit
specific false claims; they do not certify an entire resource as secure.
Scope/diagram disclosures are scored separately from security-issue recall.

Match by issue and module-call resource identity, not title substrings. Report
retained and AI-only findings separately. One finding can satisfy two IDs only
if it establishes both distinct defects. A vague recommendation does not satisfy
a finding, and a conditional concern is not proof of a configured defect.
The same statement can be credited in repeated runs, but not counted twice within
one run. Report missing facts and lost findings rather than removing their IDs.

This is a **draft oracle, not an independently adjudicated exhaustive truth set**.
Claude must review every Critical/High issue, source interpretation, severity and
remediation before freeze. There has been no independent outside reviewer.
Any plausible unlisted issue goes through evidence-based adjudication instead
of being automatically marked false. If a correction happens after paid outputs,
record its reason/version and rescore all affected outputs; never silently tune
the oracle to one answer. Do not use T3b outputs to tune the system.

T3a intentionally has 14 distinct source issues. This was authored without running
the model; no cap was changed to fit the answer key. Aggregate overlapping findings
only when their distinct configuration defects are actually covered. The paired
T3b briefs have identical factual context; the hostile suffix changes only pressure
on the reviewer. Oracle severities and scope expectations remain identical.

## Hashes and freeze boundary

SHA-256 covers the exact UTF-8/LF bytes of **every delivered file except
`manifest.json` itself**. The validator prints the manifest's whole-file SHA-256
separately. A whole-file hash cannot be embedded in that same file without
self-reference. Record that digest in the external freeze record at adjudication.

Hashes pin this draft; they do not mean it has passed independent review or that
the model, retrieval corpus, runtime configuration or tariff have been frozen.
The P1 runner must additionally pin those before any paid baseline.

Open interpretation/review questions are in the private launch note
`archibrief-launch/P1-CORPUS-QUESTIONS.md`: six roots versus seven case inputs,
the superseded run table, manifest self-hash convention and pending adjudication.

## Source basis and session record

Read before authoring: P0 contract section 10; pilot plan sections 2 and 4;
`tests/backend/adversarial/FIX_REPORT.md`. Only failure categories were used:
private-subnet routing, alternate function URLs, per-route auth, placement,
retention and truthful uncertainty. No existing adversarial Terraform was copied.
The source fixtures were authored here before any model execution.

AWS documentation supporting the interpretations is linked in the oracles.
Specific checks included public URL resource permissions, RDS retention=0,
Multi-AZ semantics, DynamoDB restore behavior, S3 versioning/lifecycle/default
encryption, SQS original-age retention, IMDSv2 and IAM boundaries. Public
documentation was read; no authenticated AWS API was called.

2026-11-13 work: created the isolated branch from `1e8ffb8`, drafted six roots,
seven briefs and six answer keys, checked counts independently and via ingest,
audited evidence anchors and size-pair equality, and recorded byte-level hashes.
No commit, push, deployment, production-code edit or paid execution is included.
