# ArchiBrief: current status

Updated 2026-11-16.

## What is live

| Part | Release | Notes |
| --- | --- | --- |
| Stakeholder Brief | PR #67 (8c90443) | Severity-first cards: Risk, Work proposed, Helps prevent, Still exposed. Commitment tiers (Light, Moderate, Major, Needs scoping), not dollar estimates. |
| First accuracy repairs | PR #68 (613ab0c) | Resource-relationship facts for the rule engine and model, plus checks that drop known unsafe fix advice (for example, a dead-letter queue on a synchronously invoked Lambda). |
| Five deterministic rules | PR #69 (9483635), `rule_engine@2026-11-16a` | API Gateway routes with no authorization (health paths exempt), unconditional public SQS/SNS publishing, AWS-managed AdministratorAccess attachments, CloudFront `allow-all` viewer protocol, literal database passwords (the value is never shown). Each has a Stakeholder Brief card. |

## Measured accuracy

R1 measured PR #68 on eight reviews: five development cases and three held-out
cases whose answer keys were not seen while building. Development and held-out
results are separate cohorts and are not pooled.

| Measure | Earlier result | R1 |
| --- | --- | --- |
| Development Critical/High caught | 31/31 (P1 baseline) | 28/31 |
| Development all-severity recall | 97.5% | 82.5% (33/40) |
| Development false claims per review | 5.2 | 3.2 |
| Development unsafe fixes per review | 1.0 | 0 |
| Held-out Critical/High caught | 10/12 (R0) | 8/12 |
| Held-out false claims per review | 2.0 | 1.67 |
| Held-out unsafe fixes per review | 0 | 0 |

R1 ran eight reviews with none failing, at $0.96 total model cost (model calls
only, not the full AWS bill).

Wrong claims and unsafe fixes went down; recall also went down. Most of the
development loss came from one review where the model returned a single finding.
The held-out issues that were lost had been caught only by the model, never by a
rule, while every rule-covered held-out issue was caught in both rounds. That is
why PR #69 added narrow rules for explicit settings. PR #69 has unit tests but
no new accuracy measurement yet.

## Not live yet

- **Independent verifier (second model pass).** Checks each model finding
  against the cited AWS passage and the declared configuration. If the check
  fails or times out, findings are kept and marked as not independently checked.
- **"Unable to verify" section.** Findings that fail a check are shown
  separately, with the reason, instead of being dropped. A fix that failed a
  safety check is withheld.
- **Review-size and cost admission.** Token counting before paid steps so a
  review that would exceed its budget is refused up front.

These ship together, with the verifier switched off at first. It is switched on
only if a paired evaluation shows no lost Critical/High catches, no fabricated
citations, no unsafe fixes kept and cost within the per-review budget.

## Further reading

- [Evaluation evidence](evaluation.md): published measurements and their limits.
- [Release readiness](release-readiness.md): what is deployed and how.
- [Architecture](architecture.md): the review pipeline and Stakeholder Brief.
- [Decision records](adr/README.md) and [project history](project-history.md).
