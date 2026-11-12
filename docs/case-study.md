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
describes the worker, the reasoning runtime and storage boundaries.

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
  carries identifiers and status only.
- **Never make the visitor come back:** the one requirement a review can't
  infer (regulatory and data residency) is asked on the form, so a review
  never pauses (ADR-0054).
- **Degrade, don't fail:** if the model step times out or errors, the report
  still ships with the deterministic findings and says the AI analysis didn't
  finish (ADR-0058).
- **Expose what cannot be known:** review the submitted static slice rather
  than equating missing code with absent organization-wide controls.

## A failure and its correction

The public demo audit found incorrect/overstated claims about S3 encryption,
CloudTrail and transfer costs. Reviewer notes corrected those claims in the UI,
but the HTML download omitted the notes and a saved answer repeated them.

Corrections now travel with HTML/JSON exports and saved answers. The fix
preserves the original generated output, identifies stale answers and checks each demo's annotation propagation with unit/browser tests.
It also replaces hardcoded snapshot versions and avoids presenting finding
type as a safety rating. [Review ledger](reviews/2026-10-23-bounded-fixes.md)

The lesson is that verification must cover the delivered artifact and its
follow-ups, not just the first report view. Passing schema and quote checks
cannot substitute for reviewing the meaning of an answer.

## Testing it like an adversary

Unit tests and trap fixtures check one thing at a time. To see how a whole
review holds up, three larger Terraform submissions were written with planted
issues, decoys and answer keys, and run through the live site. Each broke
something different ([live hard tests](evaluation.md#live-hard-tests)):

1. **A 74-resource payments platform** showed the model was blind. It only
   saw allowlisted top-level settings, so security group rules, IAM trust,
   policy actions and CloudFront origins were invisible and it guessed. The
   fix added fixed-vocabulary facts from nested configuration: enough for
   the model to reason about a role's trust and actions, but never the raw
   text, so the injection boundary holds (ADR-0056). Retrieval also moved
   from the brief alone to topic searches picked from the declared resource
   types, so findings cite specific guidance (ADR-0057).
2. **The same platform, rerun,** then failed outright: with more facts the
   model wrote more, and the call hit its 240 s read timeout. Streaming with
   an idle limit was tried first (ADR-0058) and failed live: Bedrock sends
   nothing while it builds a forced, strict tool call, so the idle limit cut
   off healthy reviews. The call now waits for the whole answer, the model's
   input is compact and bounded, the model keeps to 12 findings, and a
   failed model step falls back to a labeled rules-only report instead of
   nothing (ADR-0058, ADR-0059; [incident write-up](incidents/2026-10-29-review-timeouts.md)).
3. **A telehealth platform with a polite, lying brief** ("throwaway sandbox,
   synthetic data, cost only, reserve Critical for real incidents") passed
   Guardrails because it isn't an attack, and the model followed it. The
   code tags everything `Environment = prod` and `DataClass = phi`. The fix
   gives the model those labels from a fixed vocabulary and a rule that the
   brief can add context but never narrow scope or lower severity.
4. **A 119-resource logistics platform** showed the summary's 80-resource
   cap kept resources alphabetically, cutting every S3 bucket, security
   group and SQS policy. It now keeps access decisions first, and once the
   model's input was made compact the cap rose to 120, so that submission
   now shows every resource (ADR-0059).

The lesson: the model's ceiling is what the system shows it, and a brief is
an attack surface even when it's polite. Most misses weren't bad reasoning
about what the model saw; they were things it never saw.

## Narrowing scope to raise accuracy

The hard tests showed the next limit: a large configuration hits several
caps at once, and the model can't reason about what it never sees. In
November the project narrowed its target to small AWS workloads, with a
provisional limit of 50 resource declarations per review, counted before
any paid call ([ADR-0061](adr/0061-small-workload-accuracy-pilot.md)).
The work is ordered to measure before changing anything: reports first
state exactly what was reviewed, then a baseline is scored against answer
keys, then the limit is enforced, and only then is a second AI pass that
checks each finding tested. It ships only if it cuts wrong findings
without losing Critical or High catches. This is in progress; the full
sequence of decisions is in the [project history](project-history.md).

## Evidence and limits

[Evaluation evidence](evaluation.md) distinguishes deterministic/mocked tests
from paid model measurements. The three [real public demos](demos.md) have pinned
source provenance and manual audits, including mistakes. The bounded-fixes
review ledger records its local verification separately from older results.

The hard tests are scored by hand against their answer keys; they show
where reviews fail, not a recall rate. This does not establish recall on
arbitrary Terraform, deployed-account security, compliance, successful
restores or a hard AWS billing ceiling.
ArchiBrief now separates severity/action from evidence type,
publishes output-quality counts, assembles durable child results and runs
recoverable background deeper reviews. Its bounded observations cover placement,
routing, retention, backup selection and entry-path declarations;
[coverage and limits](terraform-coverage.md) separate those slices from unknown
runtime behavior.
The [owned retention remediation example](examples/retention-remediation/README.md)
has a measured custom-rule comparison: one targeted finding disappears and three
others remain unchanged, with no model or Terraform execution. A paired-workload
model demonstration still requires an approved measured run; no synthetic model
result is presented as evidence of contextual accuracy.
