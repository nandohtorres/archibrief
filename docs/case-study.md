# ArchiBrief engineering case study

ArchiBrief is an independent portfolio project that reviews an AWS Terraform
slice against a workload brief. Its output serves two readers: the engineer
checking the evidence and the stakeholder deciding which changes to fund.
[Source](https://github.com/nandohtorres/archibrief) ·
[Live demos](https://archibrief.dev) · [Architecture](architecture.md)

## Problem and approach

A static scanner can identify a permissive setting, but its significance also
depends on the workload's data, traffic and availability requirements. ArchiBrief
keeps repeatable checks in Trivy/custom rules, then uses retrieved AWS guidance
and a bounded resource summary to produce contextual explanations. The model
does not execute Terraform or change the user's account.

The backend uses Lambda, Step Functions and Bedrock AgentCore; the UI is a
Next.js static export on S3/CloudFront. [The architecture](architecture.md)
describes the worker, clarification callback and storage boundaries.

## Decisions that matter

- **Treat Terraform as untrusted data:** bound archive extraction and static
  parsing; do not execute providers, provisioners or fetch arbitrary modules.
- **Separate repeatable checks from synthesis:** preserve deterministic results
  independently of the model and label evidence provenance honestly.
- **Validate claims' provenance:** require model quotes to match retrieved
  passages. This establishes where text came from, not that it supports a claim.
- **Make retries safe:** bind uploads to checksums/versions, reserve estimated
  spend transactionally, and use stable execution/request identities.
- **Keep durable workflow content small:** store content in S3; Step Functions
  carries identifiers, status and clarification resume references.
- **Expose what cannot be known:** review the submitted static slice rather
  than equating missing code with absent organization-wide controls.

## A failure and its correction

The public demo audit found incorrect/overstated claims about S3 encryption,
CloudTrail and transfer costs. Reviewer notes corrected those claims in the UI,
but the HTML download omitted the notes and a saved answer repeated them.

The bounded-fixes branch makes corrections travel with HTML/JSON exports and
saved answers. It preserves the original generated output, identifies stale
answers and checks each demo's annotation propagation with unit/browser tests.
It also replaces hardcoded snapshot versions and avoids presenting finding
type as a safety rating. These changes require an approved deployment before
they describe the live site's behavior. [Review ledger](reviews/2026-10-23-bounded-fixes.md)

The lesson is that verification must cover the delivered artifact and its
follow-ups, not just the first report view. Passing schema and quote checks
cannot substitute for reviewing the meaning of an answer.

## Evidence and limits

[Evaluation evidence](evaluation.md) distinguishes deterministic/mocked tests
from paid model measurements. The three [real public demos](demos.md) have pinned
source provenance and manual audits, including mistakes. The bounded-fixes
review ledger records its local verification separately from older results.

This does not establish recall on arbitrary Terraform, deployed-account
security, compliance, successful restores or a hard AWS billing ceiling.
The local redesign branch now separates severity/action from evidence type,
publishes output-quality counts, assembles durable child results and runs
recoverable background deeper reviews. Its bounded observations cover placement,
routing, retention, backup selection and entry-path declarations;
[coverage and limits](terraform-coverage.md) separate those slices from unknown
runtime behavior. These changes still require review and deployment.
The [owned retention remediation example](examples/retention-remediation/README.md)
has a measured custom-rule comparison: one targeted finding disappears and three
others remain unchanged, with no model or Terraform execution. A paired-workload
model demonstration still requires an approved measured run; no synthetic model
result is presented as evidence of contextual accuracy.
