# ArchiBrief: accuracy and release checkpoint

Updated 2026-11-16. This describes released work and the next local candidate; it is not a deployment or paid-evaluation authorization.

## Released and local work

| Track | State | Evidence / remaining gate |
|---|---|---|
| Stakeholder Brief, theme and phone layout | Released | PR #67, 8c90443 |
| First accuracy repairs | Released and measured in R1 | PR #68, 613ab0c; backend d9b5772 |
| Five narrow deterministic rules | Released | [PR #69](https://github.com/nandohtorres/archibrief/pull/69), merge 9483635 |
| P2 admission and cost checks | In this combined local candidate | Independent review, actual free CountTokens validation, artifact/plan checks and approved deployment remain |
| P3b independent verification | In this candidate, default OFF | Same shared budget; enable only for approved evaluation/rollout |
| Unable to verify and Unsupported chat notes | Built locally; included here | Task 0 source 82e398f, on top of P3b 1a75227; independent review/release pending |
| Owner-only replay and scorecard tooling | Separate local tooling | 0721c82; not an application deployment or evidence that replay ran |

PR #69 checks explicit API Gateway authorization NONE, unconditional public queue/topic publishing, AdministratorAccess attachments, CloudFront plain HTTP and literal database passwords. The wording qualifies effective access, omits credential values and gives each concern a plain-language brief card. Claude's dynamic RULE_VERSION test fix is retained from the release merge.

## What the accuracy measurements show

These are aggregate results from Claude's generic R1 handoff, not a new judgment of sealed cases. R1 ran with P3b OFF. Development and held-out cohorts stay separate.

| Metric | Earlier comparable result | R1 |
|---|---|---|
| Development Critical/High caught | P1 baseline 31/31 | 28/31 |
| Development all-severity recall | P1 baseline 97.5% | 33/40 (82.5%) |
| Development false claims/review | P1 baseline 5.2 | 3.2 |
| Development unsafe fixes/review | P1 baseline 1.0 | 0 |
| Held-out Critical/High caught | R0 10/12 | 8/12 |
| Held-out false claims/review | R0 2.0 | 1.67 |
| Held-out unsafe fixes/review | R0 0 | 0 |

Eight R1 reviews, zero failed, $0.96 measured model total. This is not an all-service invoice. False claims and unsafe fixes improved, but recall fell: the accuracy goal is not complete. Unit-test totals are behavioral evidence, not new accuracy scores. No new scorecard row was created by this build.

Historical 43/43 citation reproduction establishes matching quotes/hashes/metadata, not semantic support. The relevance review found partial and unrelated support. New outputs still require judging.

## Decisions and reasons

- The accepted name is **Stakeholder Brief**. Risk, Work proposed, Helps prevent and Still exposed are separate. Omitted declarations are not confirmed-off controls. Commitment tiers are not price estimates; reviewer corrections stay beside findings and in downloads.
- P2 checks scope and the complete fixed request before paid AI screening/retrieval, then checks the exact assembled generation request immediately before dispatch. A missing/unavailable count or unaffordable bound stops paid AI work; it does not bypass the budget. Receipts and the existing operation deadline remain authoritative. Estimates are not whole-account invoice guarantees.
- P3b remains default OFF, enabled only by a server setting. Owner Option A fails open: a failed verifier call keeps the affected findings marked not independently checked. Verdict validation is per finding. Supported detections keep a neutral confirmation action when the proposed fix fails; contradicted detections follow the existing verifier disposition. A contradiction may cite supplied facts OR evidence; supported cited claims still require their passage. The preview4 request stays bounded to 86 KiB and does not create new findings or retrieval loops.
- Task 0 retains Reason/schema failures as a bounded separate list, withholding all recommendation/plain-action/citation fields. It does not add them to primary counts, the brief, chat grounding or go-deeper. Initial AI failure is disclosed in the same area. Unsupported chat notes remain outside future conversation history. Feeding P3b dispositions into that list is a later coordinated change; the current verifier policy is unchanged.
- Codex builds/tests and freezes local commits; Claude independently reviews/builds/plans/releases and evaluates, with Fernando's approvals. Frozen SHAs are not amended. Sealed inputs, keys and ledgers remain inaccessible to Codex.

## Combined release and evaluation path

1. Integrate released master 9483635, P2/P3b, Task 0 and the corrected public docs into one frozen candidate. This is that integration path, not a claim of production acceptance.
2. Claude reviews the exact SHA, checks real CountTokens permissions/support and artifacts, then builds/plans and deploys with P3b OFF only after the required approval and clean checks.
3. The separately authorized R2 replay proposal is capped at $1.75 and operates on R1's saved findings. Claude runs and scores it; no execution is claimed here.
4. The proposed live round uses the same eight reviews with P3b ON, temporary visitor limits and the unchanged site-wide cap. Each live/paid action still depends on its actual approval. Lower the temporary limits afterwards. Codex does not change authentication, IAM, limits or feature settings.
5. Judge against R1 and append immutable scorecard rows: no lost Critical/High catches, no fabricated citations, fewer false claims, no retained unsafe fixes and cost within the agreed budget. Keep P3b ON only if the gates pass; otherwise disable it.

The paired replay isolates verifier effects on fixed findings. The live round compares a changed package of rules, admission and verification with R1 and includes generation variance; it does not isolate the verifier's causal effect. Reusing sealed cases is an intentional matched comparison, not a fresh-case generalization claim. No extra paid arm is authorized or required by this documentation.

## Evidence and navigation

- [Evaluation evidence](evaluation.md) and [release readiness](release-readiness.md).
- [Architecture](architecture.md), [unverified claims contract](unverified-findings.md), [P2 request-budget contract](p2-request-budget.md).
- [Decision records](adr/README.md) and [project history](project-history.md).

Internal handoffs, permissions and approval records are maintained separately from this public repository. The previous docs publication hold is resolved for the rule-release identifiers: PR #69 / 9483635 are now known. The new combined candidate still requires independent review and release approval.
