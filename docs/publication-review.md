# Publication cleanup and project review

Follow-up: [the hardening report](hardening-results.md) records subsequent
behavioral fixes, toolchain upgrades and proposed retention changes. The
findings and counts below describe the earlier cleanup checkpoint; they are
retained as its audit record, not the current unresolved-issue list.

Reviewed 2026-10-17 from handoff `dc4db7a`. This continues the local
`mobile-laptop/chore/public-cleanup` work. It is an engineering review of the
checkout and local tests, not a fresh inspection of AWS or a formal security
clearance. No Terraform commands, AWS calls, paid model evaluations, pushes,
file deletions or history rewrites were performed in this continuation.

## Outcome

The infrastructure helper commit `a966e6d` was reviewed and integrated locally
as `e976869`. Its 28 edited files preserve resource/data/module configuration;
Terraform variable and output help text changed, while deployed resource
description strings were retained. Secret scanning and the offline Trivy hook
passed. Existing accepted exceptions in `.trivyignore` still apply.

Commit `442d245` completes the remaining publication text edits: operator-specific
approval messages, JSON notes, retrieval/reasoning evaluation descriptions, the
ingest User-Agent, a parser error's private-log reference, the stakeholder test
title, deleted-prototype references in ADR-0047, and stale chat documentation.
Script documentation was also made self-contained. The explicit paid-run gate
was preserved; test queries, expected chunk IDs, scoring and model settings were
not changed. README spending claims now distinguish estimated admission
reservations from a comprehensive hard cost boundary.

Source comparisons against `07685e5` checked 21 changed HCL files, 63 Python
files, two JSON files and 23 frontend source/test files. After removing comments,
docstrings, variable/output help text and the specifically reviewed descriptive
string changes, no unexpected configuration or logic changes were found.
Frontend checks compare parsed syntax trees; they are not a mathematical proof
of equivalent browser behavior. The normal test suites also ran.

## Validation

Primary compact evidence is [`evidence/publication-checks.json`](evidence/publication-checks.json).
Full local logs, XML/JSON output and the three audit reproductions remain in the
ignored `backend/build/` directory of the continuation worktree.

| Check | Result |
|---|---|
| Backend | 625 passed, 5 skipped; no failures/errors |
| Frontend unit | 56 passed in 10 files |
| Playwright | 60 passed, no skips/failures/flakes |
| TypeScript, ESLint | Passed |
| Ruff check and format, backend/scripts | Passed |
| Git whitespace and local Markdown links | Passed |
| Offline infrastructure Trivy hook | Passed configured HIGH/CRITICAL gate with accepted exceptions |
| Redacted Gitleaks scan | No configured findings across 126 commits in all local refs at scan time |
| npm audit, all dependencies | 30 findings: 2 low, 7 moderate, 19 high, 2 critical |
| npm audit, production dependencies only | 0 findings |
| Default Prettier check | Failed on 60 files; most are Windows CRLF differences |
| Prettier allowing existing line endings | One existing failure: `frontend/components/landing-intro.tsx` |
| Terraform zero-change plan | Not run; remains an operator verification step |

The component formatter issue was reported rather than modifying the component
under the earlier protected-path restriction. Python-source comparison and HCL
parsing are not substitutes for a Terraform plan. In particular, modifying a
Python comment/docstring changes source bytes, and rebuilding a Lambda ZIP can
change `source_code_hash` even when executable logic is unchanged. Do not promise
that a fresh package rebuild necessarily produces a zero-change plan.

The local runtime is Node 24.14.0 rather than the declared Node 20/22 range,
and Python 3.14 rather than CI/deployed Python 3.12. Four skips require the
gitignored corpus; a Linux-specific Trivy unit test skips on Windows. Scanner
trap tests did run in both modes. Initial sandbox attempts failed to execute
Trivy or start the browser build; approved outside-sandbox reruns resolved those
environment failures without source workarounds.

## Findings to address before anonymous access

### 1. Screening work can spend outside the atomic daily reservation

**High before public access; confirmed with a local fake Guardrail and moto.**
In `backend/lambdas/ask_question/handler.py`, `_precheck` reads counters, then
`GuardrailsClient.assess` runs before `_admit` transacts. A blocked question logs
screening cost but creates no daily spending reservation. The local probe
observed one screening call, a refused answer, no model call and an empty
counter table. Concurrent requests also share a non-atomic preliminary read.

Reserve screening before the paid call and settle/release only unused amounts.
Account for rejected inputs and dependency failures, not only successful model
answers. Keep the initial review, clarification, deeper-review and suggestion
paths under one explicit admission policy. These are implementation changes,
not part of a comment cleanup. Today's admin gate limits exposure; removing it
would materially change the threat model.

### 2. Retention is inconsistent across access paths and storage surfaces

**High before a public retention promise; replay gap reproduced locally.**
`list_questions` filters expired question items, but `ask_question` replays a
finalized request by ID without the same TTL check; the direct stored-suggestion
path also lacks a consistent expiry check. The probe expired an answered item:
GET omitted it, while POST returned the stored answer without a new model call.

Use one review-scoped absolute expiry, check it on every read/write/replay, and
never refresh sensitive content's lifetime by copying an expired suggestion.
The wider seven-day policy also needs S3 version/lifecycle cleanup and expiry
values for review/finding/audit records. Current configuration keeps Standard
workflow execution payload logging enabled with a 90-day log group; the brief
and derived findings still traverse workflow state even though parsed HCL is
stored by reference.

[DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)
deletion is asynchronous, so application access must stop independently.
[Step Functions history retention](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)
is separate from CloudWatch retention. A shorter log retention setting alone
does not establish seven-day deletion of workflow content.

### 3. Upload identity and admission still depend on the single-admin model

**Known public-launch blocker, still present in the inspected code.**
`create_upload` accepts a caller-selected review ID and signs
`uploads/{review_id}/archive.tar`. Review submission and processing need a
server-issued reservation binding the review, capability and exact object
version/hash before opening anonymous access. A reusable presigned form is not
itself a one-use storage quota. This is already a reason to keep the admin gate;
the static demo path can remain publicly useful while these controls are built.

### 4. Valid non-object JSON can cause an unhandled upload error

**Medium robustness issue, confirmed without AWS.** Calling the upload handler
with body `[]` passes JSON parsing and then raises `AttributeError` at
`payload.get`. Reject non-object JSON with a controlled 400 before accessing
fields; apply the same contract across entry points. The probe intentionally
used no credentials or live endpoint. No handler behavior was changed here.

**Status: resolved.** The upload, submit, chat and clarification handlers all
reject non-object JSON with a 400; `clarify_review` has a regression test.

### 5. Chat defaults and timeout handling need one authoritative contract

**Medium configuration/operational risk.** Terraform configures Sonnet 4.6 and
a $1.00 daily allowance; unset-environment handler fallbacks remain Haiku 4.5
and $0.40. Docs now make that distinction explicit. Centralize defaults or fail
closed on missing required deployment settings, with a test comparing config
and handler behavior.

`model_read_timeout` also returns a minimum five-second read timeout even when
less time remains. Existing tests explicitly assert that behavior. Consider a
controlled pre-call timeout when the remaining request budget cannot cover the
minimum call and final persistence. That deserves a deliberate behavioral change
and regression test, rather than being slipped into cleanup.

**Status: resolved.** Handler fallbacks now match Terraform (Sonnet 4.6, $1.00),
and `tests/backend/test_defaults_match_terraform.py` fails if they drift.
`model_read_timeout` raises a controlled timeout before the call when less than
the minimum read time remains.

## Publication and maintenance follow-ups

### Development tooling vulnerabilities deserve a separate upgrade task

The full npm audit reports critical findings in `vitest` and its `tinypool`
dependency. Production-only audit is clean, so this is not evidence that the
deployed static site is remotely exploitable. It is still relevant to developer
machines and CI. Exploit conditions matter: the reviewed
[Tinypool advisory](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3) involves a
prototype-pollution primitive; the
[Vitest UI advisory](https://github.com/advisories/GHSA-5xrq-8626-4rwp) involves
an exposed UI server. This repo uses `vitest run`, not that UI-server command.

Upgrade the test toolchain on a dedicated branch, inspect every advisory and
rerun suites on a supported Node runtime. Do not apply `npm audit fix --force`
blindly: the audit proposes major-version changes and some suggested fixes are
downgrades. Backend CVE auditing was not performed, so no Python dependency
clearance is implied.

### One private reference remains in deployed IAM metadata

`infra/modules/iam/main.tf`'s runtime boundary policy has an operator-internal
reference in its resource `description`. It was deliberately preserved: changing
resource metadata would violate the infrastructure-equivalence check and needs
its own reviewed plan. A text scanner cannot safely treat all `description`
attributes as harmless documentation. This is the remaining publication-text
exception, not a missed comment sweep.

### CI and runtime consistency are more valuable than more narrative cleanup

CI is described as advisory; this review did not inspect remote branch protection.
Its push trigger is limited to `main`/`master`, so a feature-branch push by itself
does not exercise that trigger; pull requests do. Backend CI installs unpinned
dependencies even though deployment packages have constraint files. Pin or
constrain test dependencies separately and run on the supported runtime so the
passing environment can be recreated. Frontend type checking already has a
script; consider making it an explicit CI gate as well.

Make line endings explicit in `.gitattributes` or formatter configuration in a
separate maintenance change; avoid a broad component rewrite just to make a
Windows checkout match Linux formatting. Resolve the remaining landing-component
formatting issue before claiming all CI checks are green.

### Small signs of leftover architecture

The guest-session table and review idempotency GSI are defined in infrastructure,
but the application search found no consumers of those specific structures.
Review whether they are still needed before adding more quota machinery.
Retiring deployed resources requires a separate change; nothing was deleted.
The broad shared AWS-client module and large handlers are useful future targets
for splitting by capability as public admission is introduced, rather than
adding more conditionals to already busy endpoints.

## Folder hygiene and what is working well

At the start of this continuation there were 431 tracked files; none exceeded
1 MiB. Sensitive-looking tracked names were examples (`.env.example`, frontend
env example, example tfvars and an example deploy-role policy), not real local
credentials/state. Original-checkout untracked-file inventory was empty. Local
ignored content is mostly dependencies, build products, caches, old prototypes
and the saved assistant worktrees. Those explain the much larger on-disk tree;
they are not evidence that those files will be published. Some ignored-directory
enumeration was denied by Windows permissions, and private state/env/credential
contents were intentionally not recursively read.

Gitleaks used the repository's configuration, which excludes fixture paths;
zero findings is not a proof that every historical blob or compressed archive
is free of secrets. No account IDs, keys or private file contents are reproduced
in this report. Staged changes also passed the secret-scanning hook.

The strongest parts of the project are the bounded static ingestion, real
Terraform traps, isolated scanner, typed evidence/provenance, deterministic
architecture diagrams and explicit reviewer notes on model mistakes. The
three saved demos explain the value without charging every visitor. The paid
model evaluation is still pending; the passing mocked suite is strong evidence
of software boundaries, not proof of factual model quality. Preserve that
distinction in public presentation.

The most useful next sequence is: settle the remaining publication exceptions,
complete the bounded paid quality/trap evaluation under separate authorization,
then implement and test public admission/retention. More agents or more features
will not resolve the identified cost and expiry gaps by themselves.
