# ArchiBrief: current status and accuracy direction

Updated 2026-11-16. This is a documentation checkpoint, not a deployment or paid-evaluation authorization.

## Product goal and working split

Make the review more accurate across detection, explanation, safe remediation and citation support, while making the Stakeholder Brief understandable to a nontechnical decision-maker. Clear presentation must not imply that a model claim has been independently proved.

Codex builds and tests, then freezes immutable local commits. Claude independently reviews those exact commits, builds/plans/releases with Fernando's approval for live steps, and owns paid evaluations, judging and scorecard rows. No push is implied by a local commit. Handoffs live in `handoffs/`.

## What has shipped, and what has not

| Track                            | Status at this checkpoint                                                                                          | Evidence / next gate                                                                                                 |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Stakeholder Brief                | Released in PR #67, revision 8c90443; theme-before-paint and phone arrow included                                  | Owner supplied Claude's production verification; not rechecked against AWS in this docs pass                         |
| First accuracy repairs           | PR #68 merge 613ab0c exists locally; Claude's R1 handoff identifies backend d9b5772, P3b off                       | R1 measures this build, not the newer candidates below                                                               |
| Five narrow deterministic rules  | Frozen, local only: 091ee100235aa2ed32744a7326a0be89e3565060, feat/deterministic-accuracy-rules                    | Claude independent review, package/plan/release, then evaluation                                                     |
| P2 scope/request/cost admission  | Implemented in combined integration, not release-accepted                                                          | Real CountTokens/cost admission, auxiliary-cost assumptions and reviewed infrastructure/artifact checks still needed |
| P3b independent verifier         | Frozen, default off: 1a752273cf26189cffde691c4bebcf9b2aa0b6c6, feat/p2-stakeholder-integration                     | P2 prerequisite, independent review and approved paired evaluation before enablement                                 |
| Owner replay / scorecard tooling | Frozen, local only: 0721c82819e1ed4f0b6f6859d1cd2dfea33a46d8, feat/owner-evaluation-tools                          | Claude operates on authorized review IDs; Codex has not run real review replay or AWS metric reads                   |
| Citation audit                   | Historical 43/43 citations reproduce quote/hash/metadata; initial relevance review found partial/unrelated support | Reproduction is not entailment or a pass for future output                                                           |

The three frozen candidates remain unchanged. Documentation is prepared separately; it does not become part of those reviewed SHAs. Local master refs can be stale: compare release diffs to the actual deployed base before publishing.

## Accuracy: measured progress and remaining shortfall

The following are aggregate results from Claude's explicitly supplied R1 handoff, not a new Codex judgment or a read of sealed cases. Cohorts and versions must stay separate.

| Measure                         | Earlier comparable result | R1 (P3b off)  |
| ------------------------------- | ------------------------- | ------------- |
| Development Critical/High       | P1 baseline 31/31         | 28/31         |
| Development all-severity recall | P1 baseline 97.5%         | 33/40 (82.5%) |
| Development false claims/review | P1 baseline 5.2           | 3.2           |
| Development unsafe fixes/review | P1 baseline 1.0           | 0             |
| Held-out Critical/High          | R0 10/12                  | 8/12          |
| Held-out false claims/review    | R0 2.0                    | 1.67          |
| Held-out unsafe fixes/review    | R0 0                      | 0             |

R1: eight reviews, zero failed, $0.96 measured model cost in aggregate. This is not an all-service invoice total. The historical baseline cost remains estimated; missing end-to-end timing must remain unknown rather than be inferred from model time.

Interpretation: wrong claims and unsafe fixes improved, but recall fell. Do not claim the accuracy goal is met or call this an unqualified improvement. The reported development recall loss was concentrated in one unusually short model response; the held-out lost catches were model-only. Their cause is not established by these aggregates. Across R0/R1 the rule-covered held-out issues were caught both times, motivating narrow configuration rules rather than relying solely on generation variability. Unit tests do not prove a new accuracy rate.

## Decisions, reasons and boundaries

- **Stakeholder Brief** is the accepted name. Severity-first cards explain Risk, Work proposed, Helps prevent and Still exposed. Conditional evidence wording distinguishes absent declarations from controls confirmed off. Analogies are limited to curated rule concerns. Costs use commitment tiers, not dollar estimates; reviewer corrections remain beside findings, including exports. Public output filtering covers generated/cached chat and downloads without rewriting stored evidence.
- **Split releases:** presentational work and narrow accuracy repairs can ship without P2. P3b's production adapter depends on P2 budget/admission wiring, so it cannot be enabled independently. This avoids making low-risk repairs wait for infrastructure validation.
- **Fail open (owner Option A):** failed, malformed, missing or oversized verification leaves affected findings Not independently checked, with incomplete metadata. Each verdict is validated separately. One bad verdict must not invalidate valid siblings.
- **Detection and fix are separate:** a supported detection with an unsafe/unworkable fix is retained with a neutral confirmation action. A valid contradicted detection is removed under the current frozen implementation. Contradiction can be established by supplied fact IDs OR evidence IDs. Supported cited detections still need their cited source support. Every supplied ID is checked.
- **Bounded verifier:** preview4 sends claim fields, mentioned resources plus one reference step, and cited passages only. It prioritizes what fits the unchanged 86 KiB bound, keeps excluded findings unchecked and never drops findings merely for size. Oversized reviews plan zero calls rather than refusing an entire replay batch. No new retrieval, tools, findings or corrective generation loops.
- **Narrow deterministic additions:** explicit unauthenticated API Gateway routes/methods, unconditional public SQS/SNS publishing, exact AWS-managed AdministratorAccess attachments, CloudFront allow-all viewer protocol and literal database credentials. Effective-access wording is qualified; no password value is emitted by the new finding. These are explicit settings, not guesses that omitted/unresolved settings are off. Each has a concern, severity and plain-language card; unsupported commitment sizing is Needs scoping.
- **Protect evaluation validity:** Codex does not inspect sealed inputs, keys, ledgers or logs. The R0/R1 cohort stays sealed through paired R2; replaying the same saved findings is an intentional control, not a fresh holdout claim. Fresh cohorts are needed for later generalization. Do not tune withheld bug families before their authorized replay is scored.
- **Paid/AWS approvals:** the free CountTokens payload transfer and scoped permission update were approved, but the available identity lacked administrator access. That is an access blocker, not pending owner approval for that same permission change. It authorizes no paid evaluation. Future paid execution needs a frozen plan/hash, approved cap and stop rules; no new spend was made here.

## Validation on the latest candidates

| Candidate                  | Offline validation                                                                                             |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- |
| P3b contract fix           | 39 production verifier/shared tests; 23 replay/shared tests; Ruff; matching shared protocol bytes              |
| Five rules + brief entries | 87 new synthetic cases within 417 backend tests; 130 frontend tests; typecheck, lint, formatting; commit hooks |

Counts are candidate-specific, overlap and must not be added into a product-wide accuracy denominator. Hosted CI, production package builds, Terraform plan, Linux cold start and browser validation for these latest SHAs are Claude's release checks; no new pass is claimed here.

## Next work, in order

1. Claude reviews the two build tasks at the frozen SHAs. The deterministic rule commit can take the independent release path; compare against deployed backend d9b5772 / merge 613ab0c, not stale local master.
2. Implement the owner-requested **Unable to verify** follow-up from Task 0 in a separately coordinated change in Claude's generic R1 handoff. It was not included in the owner's Task 1 then Task 2 build instruction. Keeping rejected candidates in a separate, excluded-from-totals section requires a distinct schema/report/chat/frontend change and explicit reconciliation with the frozen verifier dispositions. Do not describe it as already built or silently change the current contradiction policy.
3. Complete P2's real admission/cost evidence and independent release validation. Keep P3b off until these prerequisites and rollout approval are satisfied.
4. Claude prepares/runs the approved R2 paired replay on the same saved findings, with off/on controls and per-finding dispositions. About $1.60 was proposed in the generic handoff, not newly authorized. If generation allocation changes, retain the matched reduced-token generator-only control.
5. Judge detection, unsupported claims, unsafe fixes, lost Critical/High catches, citation support, cost and model/end-to-end time separately; append immutable scorecard rows. Zero lost Critical/High catches, zero fabricated citations, zero retained unsafe fixes and the accepted per-review budget remain verifier gates. Inconclusive results keep P3b off.
6. Only after scoring, consider withheld bug classes, trade-off-aware rules, richer omitted/off/unresolved setting metadata and further prompt changes. These are follow-ups, not completed work or this release's scope.

## Evidence and navigation

- Generic R1 results and outstanding Task 0: [Claude's handoff](../../archibrief-launch/handoffs/2026-11-16-claude-r1-results-codex-next.md).
- Exact builds: [P3b contract handoff](../../archibrief-launch/handoffs/2026-11-16-p3b-verdict-contract-fix.md), [five-rule handoff](../../archibrief-launch/handoffs/2026-11-16-deterministic-accuracy-rules.md).
- [Decision log](../../archibrief-launch/PILOT-DECISION-LOG.md), [scorecard specification](../../archibrief-launch/evaluations/SCORECARD.md), [scorecard command](../../archibrief-launch/evaluations/SCORECARD-COMMAND-2026-11-16.md), [evaluation plan](../../archibrief-launch/P3B-EVALUATION-PLAN-2026-11-16.md).
- [Citation review](../../archibrief-launch/CITATION-REVIEW-2026-11-16.md), [P2 progress and access blocker](../../archibrief-launch/P2-IMPLEMENTATION-PROGRESS-2026-11-15.md), [release checklist](../../archibrief-launch/ACCURACY-RELEASE-DEPLOY-CHECKLIST-2026-11-16.md).

Dated reviews, captured SHAs, scorecard rows and old journals are evidence snapshots. Forward pointers supersede stale present-tense status without rewriting those records. No sealed artifacts or scorecard JSON were opened during this documentation audit.
