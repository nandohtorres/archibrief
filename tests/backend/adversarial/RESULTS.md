# Adversarial run: results and defects

**Update, 2026-10-22:** the original baseline record below is retained.
See [After fixes](#after-fixes-2026-10-22) and [the fix report](FIX_REPORT.md)
for the completed local fixes and current results. Descriptions of defects
and uncommitted files in the baseline section describe the original run.

**Run:** 2026-10-20, worktree branch `mobile-laptop/test/adversarial-fixtures`
(based on `963c887`). Backend venv Python 3.14; offline Trivy 0.76.0
(`--skip-check-update`, the scanner's own isolated environment). No AWS,
model or terraform calls. Answer key frozen before evaluation (SHA-256
`577c4343…`, README "Freeze record").

**Headline:** 204 frozen checks × mode in families 1-9, plus 28 boundary
cases in family 10. Twenty defects, six of them high severity. The
deterministic layer is strong on what it was built for: no instruction text
or secret marker leaked anywhere; findings were identical with and without
injection text; archive, summary and diagram bounds held and were
disclosed. It is weakest where the code's **meaning** depends on Terraform
semantics it doesn't model: variable files, module calls, launch-time
overrides, policy-document conditions, and where a silent cap drops evidence.

Full per-check table with expected versus observed text:
[results/results_table.md](results/results_table.md). Raw verdicts:
[results/results.json](results/results.json).

## Metrics (measured, deterministic layer only)

| Measure | Rules only | Trivy + rules | Notes |
|---|---|---|---|
| Recall: rule-covered defects detected | 16/24 (67%) | 16/24 (67%) | Misses: F01-D-01, F01-D-07, F02-D-06, F02-D-10/11/12, F03-D-01, F03-D-03 |
| False claims avoided (rule-covered) | 25/29 | 25/29 | 4 false claims: F01-D-02, F02-D-08, F02-C-03, F02-D-13. Of the 25 passes, 3 are vacuous (F03-D-04/05/06, B2) and 1 is right for the wrong reason (F02-D-05, B15) |
| Attribution correct | 4/6 adjudicated (3/6 raw) | 4/6 (3/6) | Fails: F03-D-02 (role link lost to B2), F09-D-05 (name collision). Trivy mode adds B18 outside the key |
| Uncertainty and gaps disclosed | 1/8 | 2/8 | Remote modules, unresolved module inputs, scanner and backup truncation never disclosed. Trivy evaluates the conditional `count` correctly (F01-D-08) |
| Other evidence handling | 13/20 | 13/20 | Uncalled and count = 0 modules reported as deployed; neutralization miss; summary truncation of backup rules |
| Coverage-gap expectations | 0/13 adjudicated (4/13 raw) | 0/13 | The 4 raw passes only found an empty summary entry (Adjudication) |
| Family 10 boundary cases | 25/28 pass | — | Fails: scanner cap 201 (simulated), scanner cap with real Trivy, backup rules 11 |
| Citation provenance | **not measured** | | Deterministic findings carry no citations |
| Semantic support | **not measured** | | Needs the model run (NOT RUN) |

Rejected findings and failed reviews: none occurred in this run. The
deterministic path rejects nothing; Validate (which rejects model findings)
wasn't exercised because no model ran. The malformed cases were rejected
explicitly, as expected, and are counted in family 10.

## Results per check

Verdicts per mode. Full expected/observed text: results/results_table.md.

| Check | Case | Kind / scope | Expected (short) | rules | trivy | Adjudicated / note |
|---|---|---|---|---|---|---|
| F01-D-01 | F01-dangerous | must_detect / rule_covered | production.auto.tfvars sets db_public = true, so the database is publicly accessible | fail | fail | fail |
| F01-D-02 | F01-dangerous | must_not_claim / rule_covered | The summary must not tell the model publicly_accessible is false when the auto-loaded tfvars se | fail | fail | fail |
| F01-D-03 | F01-dangerous | must_not_claim / evidence_handling | No module block calls modules/unused_legacy, so its open SSH group is never created | fail | fail | fail |
| F01-D-04 | F01-dangerous | must_not_claim / evidence_handling | The uncalled module's public database is never created | fail | fail | fail |
| F01-D-05 | F01-dangerous | must_not_claim / evidence_handling | The resource summary must not list a resource from an uncalled module as something the code cre | pass | pass | pass |
| F01-D-06 | F01-dangerous | must_not_claim / evidence_handling | module "archive" has count = 0, so its bucket is never created | fail | fail | fail |
| F01-D-07 | F01-dangerous | must_detect / rule_covered | module.edge_lab passes open_admin = true, so its admin group opens SSH to 0.0.0.0/0 | fail | fail | fail |
| F01-D-08 | F01-dangerous | must_not_claim / evidence_handling | count = var.enable_debug_sg ? 1 : 0 with default false and no tfvars override: not created. Sta | fail | pass | rules fail, trivy pass |
| F01-D-09 | F01-dangerous | must_disclose / evidence_handling | Registry module contents are not in the archive | fail | fail | fail |
| F01-D-10 | F01-dangerous | must_disclose / evidence_handling | Git module contents are not in the archive | fail | fail | fail |
| F01-C-01 | F01-corrected | must_not_claim / rule_covered | tfvars sets db_public = false | pass | pass | pass |
| F01-C-02 | F01-corrected | must_detect / evidence_handling | The summary reports publicly_accessible = false (default and tfvars agree) | pass | pass | pass |
| F01-C-03 | F01-corrected | must_not_claim / rule_covered | Both module calls pass open_admin = false | pass | pass | pass |
| F01-C-04 | F01-corrected | must_not_claim / evidence_handling | count = 0 module | fail | fail | fail |
| F01-I-01 | F01-incomplete | must_disclose / evidence_handling | var.db_public has no default and no tfvars: the value is unknown and must be reported as unknow | pass | pass | pass |
| F01-I-02 | F01-incomplete | acceptable_uncertainty / rule_covered | No public-access finding is acceptable, since the value is unknown | pass (acceptable either way) | pass (acceptable either way) | pass (acceptable either way) |
| F01-I-03 | F01-incomplete | must_disclose / evidence_handling | Remote module contents unavailable | fail | fail | fail |
| F02-D-01 | F02-dangerous | must_detect / rule_covered | Full admin, literal JSON heredoc | pass | pass | pass |
| F02-D-02 | F02-dangerous | must_detect / rule_covered | Full admin, jsonencode() | pass | pass | pass |
| F02-D-03 | F02-dangerous | must_detect / rule_covered | Full admin, aws_iam_policy_document | pass | pass | pass |
| F02-D-04 | F02-dangerous | must_not_claim / rule_covered | Principal * restricted by aws:SourceVpce is not 'anyone' | pass | pass | pass |
| F02-D-05 | F02-dangerous | must_not_claim / rule_covered | Same restriction written as aws_iam_policy_document | pass | pass | pass (wrong reason) — Not flagged only because a policy document's principals type "*" isn't recognised as public at all (post-freeze probe 1); the dropped Condition never mattered |
| F02-D-06 | F02-dangerous | must_detect / rule_covered | aws:SecureTransport only requires HTTPS | fail | fail | fail |
| F02-D-07 | F02-dangerous | must_not_claim / rule_covered | Trust carries sts:ExternalId | pass | pass | pass |
| F02-D-08 | F02-dangerous | must_not_claim / rule_covered | Same trust and ExternalId condition via aws_iam_policy_document | fail | fail | fail |
| F02-D-09 | F02-dangerous | must_not_claim / rule_covered | A Deny statement grants nothing | pass | pass | pass |
| F02-D-10 | F02-dangerous | must_detect / rule_covered | Allow + NotAction [iam:*, organizations:*] on Resource * grants nearly every action | fail | fail | fail |
| F02-D-11 | F02-dangerous | must_detect / rule_covered | Same NotAction grant via policy document (not_actions) | fail | fail | fail |
| F02-D-12 | F02-dangerous | must_detect / rule_covered | Allow s3:* with NotResource on one bucket = s3:* on every other bucket | fail | fail | fail |
| F02-D-13 | F02-dangerous | must_not_claim / rule_covered | A permissions boundary caps the role at s3:GetObject on one bucket | fail | fail | fail |
| F02-D-14 | F02-dangerous | acceptable_uncertainty / rule_covered | Flagging the unattached policy's content is acceptable | pass (acceptable either way) | pass (acceptable either way) | pass (acceptable either way) |
| F02-D-15 | F02-dangerous | must_not_claim / rule_covered | The policy is attached to nothing | fail | fail | pass — Probe artifact: 'role' matched the rule's generic recommendation text (' |
| F02-C-01 | F02-corrected | must_not_claim / rule_covered | Scoped policies | pass | pass | pass |
| F02-C-02 | F02-corrected | must_not_claim / rule_covered | VPC-endpoint-restricted policy document | pass | pass | pass |
| F02-C-03 | F02-corrected | must_not_claim / rule_covered | ExternalId trust via policy document | fail | fail | fail |
| F02-C-04 | F02-corrected | must_not_claim / rule_covered | Deny-only guardrail | pass | pass | pass |
| F02-C-05 | F02-corrected | must_not_claim / rule_covered | EC2 role with a scoped customer policy | pass | pass | pass |
| F02-I-01 | F02-incomplete | must_not_claim / rule_covered | The policy text is unknown | pass | pass | pass |
| F03-D-01 | F03-dangerous | must_detect / rule_covered | http_tokens = "optional" set at launch overrides the us-east-1 account default (launch values t | fail | fail | fail |
| F03-D-02 | F03-dangerous | must_detect / rule_covered | The IMDS finding links the instance to its broad role (proxy_role, AmazonS3FullAccess) | fail | fail | fail |
| F03-D-03 | F03-dangerous | must_detect / rule_covered | In us-west-2 with no metadata_options | fail | fail | fail |
| F03-D-04 | F03-dangerous | must_not_claim / rule_covered | Requires tokens | pass | pass | pass (vacuous) — Every IMDS finding is suppressed by the account default (B2) |
| F03-D-05 | F03-dangerous | must_not_claim / rule_covered | Metadata endpoint disabled | pass | pass | pass (vacuous) — Every IMDS finding is suppressed by the account default (B2) |
| F03-D-06 | F03-dangerous | must_not_claim / rule_covered | modern_api uses api_role, not the broad proxy_role | pass | pass | pass (vacuous) — Every IMDS finding is suppressed by the account default (B2) |
| F03-D-07 | F03-dangerous | must_detect / rule_covered | EC2 role with AmazonS3FullAccess | pass | pass | pass |
| F03-C-01 | F03-corrected | must_not_claim / rule_covered | Requires tokens | pass | pass | pass |
| F03-C-02 | F03-corrected | must_not_claim / rule_covered | Unset in us-east-1, where the account default requires tokens | pass | pass | pass |
| F03-C-03 | F03-corrected | must_not_claim / rule_covered | Endpoint disabled | pass | pass | pass |
| F03-I-01 | F03-incomplete | must_detect / rule_covered | The account default comes from a variable with no default | pass | pass | pass |
| F04-D-01 | F04-dangerous | must_detect / rule_covered | SSH open to ::/0 on an attached group | pass | pass | pass |
| F04-D-02 | F04-dangerous | must_detect / rule_covered | publicly_accessible = true | pass | pass | pass |
| F04-D-03 | F04-dangerous | must_detect / rule_covered | Postgres open to 0.0.0.0/0 in the payments module | pass | pass | pass |
| F04-D-04 | F04-dangerous | must_not_claim / rule_covered | Root db group allows 5432 only from the app security group | pass | pass | pass |
| F04-D-05 | F04-dangerous | must_not_claim / rule_covered | Reporting module's db group allows 10.0.0.0/16 only | pass | pass | pass |
| F04-D-06 | F04-dangerous | must_not_claim / evidence_handling | The group is attached to nothing | fail | fail | fail |
| F04-D-07 | F04-dangerous | must_detect / coverage_gap | Named private, but its route table sends 0.0.0.0/0 to the internet gateway | fail | fail | fail |
| F04-D-08 | F04-dangerous | must_not_claim / evidence_handling | The diagram must not draw an internet edge to the root db group (SG-to-SG only) | pass | pass | pass |
| F04-D-09 | F04-dangerous | must_detect / evidence_handling | The diagram draws the internet edge to the ::/0 group | pass | pass | pass |
| F04-C-01 | F04-corrected | must_not_claim / rule_covered | SSH restricted to one IPv6 range | pass | pass | pass |
| F04-C-02 | F04-corrected | must_not_claim / rule_covered | Not public | pass | pass | pass |
| F04-C-03 | F04-corrected | must_not_claim / rule_covered | Both modules restricted | pass | pass | pass |
| F04-I-01 | F04-incomplete | must_not_claim / rule_covered | The allowed ranges are unknown | pass | pass | pass |
| F05-D-01 | F05-dangerous | must_detect / evidence_handling | The summary reports three copies | pass | pass | pass |
| F05-D-02 | F05-dangerous | must_disclose / coverage_gap | All three instances are pinned to us-east-1a | fail | fail | fail |
| F05-D-03 | F05-dangerous | must_disclose / coverage_gap | The "dr" replica's provider is in us-east-1, the same Region as the primary | fail | fail | fail |
| F05-D-04 | F05-dangerous | must_not_claim / rule_covered | No deterministic output may say the design is cross-Region or meets the RTO/RPO | pass | pass | pass |
| F05-C-01 | F05-corrected | must_disclose / coverage_gap | Placement across three AZs should be visible | fail | fail | fail |
| F05-C-02 | F05-corrected | must_disclose / coverage_gap | The replica's Region (us-west-2) should be visible | fail | fail | fail |
| F05-I-01 | F05-incomplete | must_detect / evidence_handling | count = 2 is known even though placement isn't | pass | pass | pass |
| F06-D-01 | F06-dangerous | must_disclose / evidence_handling | The plan has 11 rules | fail | fail | fail |
| F06-D-02 | F06-dangerous | must_detect / evidence_handling | The decisive 11th rule (the only copy, kept 1 day, against a 30-day audit need) must be visible | fail | fail | fail |
| F06-D-03 | F06-dangerous | must_disclose / coverage_gap | The only selection assigns dev_sandbox | pass | pass | fail — Probe weaker than intent: the selection appears in the summary with empty settings, so which resources it protects is still invisible |
| F06-D-04 | F06-dangerous | must_not_claim / evidence_handling | A copy to another vault must not be described as another Region or account | pass | pass | pass |
| F06-C-01 | F06-corrected | must_detect / evidence_handling | All four rules visible, including the copy | pass | pass | pass |
| F06-I-01 | F06-incomplete | must_disclose / coverage_gap | Which resources are protected is unknown | pass | pass | fail — Same as F06-D-03: entry present, nothing about what it selects |
| F07-D-01 | F07-dangerous | must_detect / rule_covered | Paid-model function with no reserved concurrency | pass | pass | pass |
| F07-D-02 | F07-dangerous | must_detect / rule_covered | Stage with no throttling method settings | pass | pass | pass |
| F07-D-03 | F07-dangerous | must_detect / coverage_gap | A public function URL (authorization NONE) is a second paid entry path that bypasses CloudFront | fail | fail | fail |
| F07-D-04 | F07-dangerous | must_detect / coverage_gap | POST /batch has authorization NONE while /chat uses the authorizer | fail | fail | fail |
| F07-D-05 | F07-dangerous | must_detect / coverage_gap | The diagram should connect the internet to the public function URL | fail | fail | fail |
| F07-D-06 | F07-dangerous | must_not_claim / rule_covered | No deterministic output may present the budget as a spending cap | pass | pass | pass |
| F07-C-01 | F07-corrected | must_not_claim / rule_covered | Reserved concurrency set | pass | pass | pass |
| F07-C-02 | F07-corrected | must_not_claim / rule_covered | Throttling configured | pass | pass | pass |
| F07-I-01 | F07-incomplete | must_detect / rule_covered | Reserved concurrency still unset | pass | pass | pass |
| F08-D-01 | F08-dangerous | must_disclose / coverage_gap | Expiration on a versioned bucket only adds a delete marker | pass | pass | fail — Probe weaker than intent: the lifecycle configuration appears with empty settings; no expiration or noncurrent-version data reaches the model |
| F08-D-02 | F08-dangerous | must_disclose / coverage_gap | TTL is enabled but nothing shows a writer | fail | fail | fail |
| F08-D-03 | F08-dangerous | must_not_claim / evidence_handling | retention_in_days unset means logs never expire | fail | fail | fail |
| F08-D-04 | F08-dangerous | must_not_claim / rule_covered | The bucket is versioned | pass | pass | pass |
| F08-C-01 | F08-corrected | must_detect / evidence_handling | retention_in_days = 7 is reported | pass | pass | pass |
| F08-I-01 | F08-incomplete | must_disclose / coverage_gap | Expiry days come from a variable | pass | pass | fail — Same as F08-D-01 |
| F09-D-01 | F09-dangerous | must_detect / rule_covered | SSH open to the internet, despite the description and tag | pass | pass | pass |
| F09-D-02 | F09-dangerous | must_detect / rule_covered | Public bucket policy, despite the comments | pass | pass | pass |
| F09-D-03 | F09-dangerous | must_detect / rule_covered | IMDSv2 not required, despite the user_data text | pass | pass | pass |
| F09-D-04 | F09-dangerous | must_detect / rule_covered | Secret-like environment variable | pass | pass | pass |
| F09-D-05 | F09-dangerous | must_detect / evidence_handling | The public finding for region_a must be attributable: the two names may not collapse to one dis | fail | fail | fail |
| F09-D-06 | F09-dangerous | must_not_claim / evidence_handling | Instruction text from descriptions, tags, heredocs and comments must not reach parsed comments, | pass | pass | pass |
| F09-D-07 | F09-dangerous | must_not_claim / evidence_handling | Synthetic secret markers must not reach findings, the summary, the diagram or the report | pass | pass | pass |
| F09-D-08 | F09-dangerous | must_detect / evidence_handling | Every non-local source is rewritten before Trivy runs: one-line blocks, odd spacing, s3::, outs | fail | fail | fail |
| F09-D-09 | F09-dangerous | must_disclose / evidence_handling | Remote and out-of-archive module contents are recorded as not observable | fail | fail | fail |
| F09-D-10 | F09-dangerous | must_detect / evidence_handling | The same defects without instruction text (variant control) give the same set of findings | pass | pass | pass |
| F09-K-01 | F09-control | must_detect / rule_covered | Same SSH defect without injection text (control for F09-D-10) | pass | pass | pass |
| F09-K-02 | F09-control | must_not_claim / evidence_handling | Secret markers still absent | pass | pass | pass |

## Adjudication

Raw verdicts are unchanged; these notes explain verdicts the frozen probe
got wrong.

- **F02-D-15 (fail → pass):** "role" matched the rule's generic recommendation
  ("…the role actually needs"), not a claim that the unattached policy is held.
- **F02-D-05 (pass, wrong reason):** the policy-document bucket policy isn't
  flagged because `principals { type = "*" }` isn't recognised as public at
  all (B15), so B1's dropped Condition never surfaced on this check.
- **F03-D-04/05/06 (pass, vacuous):** B2 suppresses every IMDS finding, so
  "don't flag modern_api" passes trivially.
- **F06-D-03, F06-I-01, F08-D-01, F08-I-01 (pass → fail):** the probe only
  checked that a summary entry exists. Every created resource gets one, but
  with empty settings, so the selection's targets and the lifecycle rules
  still never reach the model.

## Defects

Severity: **High** means a confident wrong statement, or a missed defect
inside a concern the system claims to cover, or a security control that
doesn't hold. **Medium** means wrong attribution, an overstated claim, or
undisclosed missing evidence. **Low** means wording or edge cases.

### B1 (High). `render_policy_document` drops Condition, NotAction, NotResource and NotPrincipal
- **Repro:** F02-D-08 and F02-C-03. `partner_doc` trusts account 111122223333
  with an `sts:ExternalId` condition written as an `aws_iam_policy_document`,
  and is flagged "assume-role policy has no external-id/federation
  condition". The literal-JSON twin `partner_json` (F02-D-07) is not.
  F02-D-11: `not_actions` vanish, so `almost_admin_doc` renders with an empty
  Action list.
- **Code:** `backend/lambdas/rule_engine/hcl_eval.py:85-105`. Only effect,
  actions, resources and principals are copied.
- **Impact:** equivalent policies get opposite conclusions. A correct trust
  policy is reported as a defect in the corrected variant (a false positive
  on good code), and conditions on bucket policies written as documents are
  invisible to `rule_s3_bucket_policy_public`.
- **Suggested fix:** render `condition` blocks to `{"Condition": {test: {variable: values}}}`
  (several blocks merge; the same test and variable AND together), and
  `not_actions`/`not_resources`/`not_principals` to NotAction, NotResource and
  NotPrincipal. Add policy-document twins of the t* traps.

### B2 (High). An account IMDS default suppresses every instance, including explicit `http_tokens = "optional"` and other Regions
- **Repro:** F03-D-01, F03-D-02, F03-D-03 (both modes; Trivy's AWS-0028 isn't
  trusted, so the own rule runs in both). `legacy_proxy` sets `optional` at
  launch and has the AmazonS3FullAccess role; `west_worker` runs in us-west-2.
  Neither is flagged, and the IMDS-to-broad-role link disappears.
- **Code:** `backend/lambdas/rule_engine/handler.py:784-800`. `if _account_requires_imdsv2(parsed): return []`.
- **Impact:** misses the Capital One-style chain the product highlights. Per
  the EC2 docs, launch values override account defaults, and defaults are per Region.
- **Suggested fix:** skip only instances whose `http_tokens` is unset and whose
  provider Region matches the default's Region (provider alias or `region`).
  Always flag an explicit `optional`.

### B3 (High). `*.auto.tfvars` and `terraform.tfvars` values are ignored; variable defaults are reported as facts
- **Repro:** F01-D-01 and F01-D-02. `production.auto.tfvars` sets `db_public = true`.
  No finding, and the summary tells the model `publicly_accessible: false`.
- **Code:** `backend/lambdas/ingest/handler.py:79-116` (a tfvars file is
  parsed, but only blocks are read) and `hcl_eval.py:55-59` (`var.x` resolves
  to `default`).
- **Impact:** a public production database is described to the model as
  private, a confident wrong fact.
- **Suggested fix:** load `terraform.tfvars`, `terraform.tfvars.json` and
  `*.auto.tfvars(.json)` in Terraform's order and resolve root variables from
  them first. When other `.tfvars` files are present (likely `-var-file`
  input), resolve to "unknown", not to the default.

### B4 (High). Module blocks are never read: uncalled modules count as deployed, module `count = 0` is ignored, and inputs aren't bound
- **Repro:** F01-D-03, F01-D-04, F01-D-05 (uncalled `modules/unused_legacy`
  reported in findings and the summary). F01-D-06 and F01-C-04 (`module "archive" { count = 0 }`
  still produces bucket findings, in the corrected variant too). F01-D-07
  (`module.edge_lab` passes `open_admin = true`, but the rules see the
  module's default and stay silent). Trivy mode shares the uncalled-module
  behaviour (it scans every directory) and does resolve `edge_lab`, but see B18.
- **Code:** `backend/lambdas/ingest/handler.py:73-116` (`document["module"]`
  is never read), and `backend/shared/terraform_scope.py` (resources are keyed
  by directory, not by module call).
- **Impact:** findings from dead code on the corrected variant, and missed
  exposures that depend on module inputs.
- **Suggested fix:** walk module calls from the root. Only directories reached
  by a local `source` are instantiated, `count`/`for_each` apply to module
  calls, and resources are keyed per call (`edge_lab/admin`) with that call's
  inputs bound. List uncalled directories as "declared but not called".

### B5 (Medium). Remote module contents are never recorded as unobserved; `not_observable` is dead data
- **Repro:** F01-D-09, F01-D-10, F01-I-03, F09-D-09. `parsed["not_observable"]`
  is `[]` for registry, `git::`, `s3::` and out-of-archive sources.
- **Code:** `backend/lambdas/ingest/handler.py:95` checks resource bodies,
  never module blocks. Nothing in `rule_engine`, `agent` or `report` reads
  `not_observable`.
- **Impact:** a report on a mostly-remote-module stack doesn't say most of the
  stack was never reviewed.
- **Suggested fix:** record module calls with non-local sources (including
  registry shorthand `ns/name/provider` and local paths outside the archive),
  and turn them into a not-observable finding and a summary note.

### B6 (High, security control). Remote-source neutralization misses one-line module blocks
- **Repro:** F09-D-08. `module "oneline" { source = "git::https://example.invalid/one-line.git" }`
  is left unchanged and handed to Trivy. Every multi-line variant
  (`s3::`, odd spacing, `../../outside-root`, a registry host) was rewritten.
- **Code:** `backend/lambdas/scan/handler.py:46`. `_SOURCE_ATTRIBUTE` is
  anchored with `^\s*source`.
- **Impact:** the guard that stops a submitter making the scanner fetch an
  attacker-chosen URL can be bypassed with valid HCL. What remains are the
  dead HTTP(S) proxy and whatever download tooling the Lambda lacks. This run
  can't prove no fetch was attempted, only that nothing could resolve
  (`.invalid`).
- **Suggested fix:** locate module sources structurally (hcl2 module blocks →
  attribute positions), or match `source\s*=` anywhere inside a `module` block
  body. Add the one-line form to the trap suite.

### B7 (High). The scanner's 200-result cap is silent, and drops findings for concerns Trivy owns
- **Repro:** F10-T-201 (simulated report) and F10-T-real (offline Trivy, 50
  buckets plus a public RDS instance in the last file). The scanner result
  has no truncation field, and the public-database finding is gone, because
  Trivy owns `rds_public` and the matching ArchiBrief rule stands down.
- **Code:** `backend/lambdas/scan/handler.py:175-176` and
  `backend/lambdas/rule_engine/handler.py:1061-1062`.
- **Impact:** a large but ordinary submission (around 40 buckets) silently
  loses later, possibly critical, findings.
- **Suggested fix:** return `truncated` and the total count. When truncated,
  run the own rules for Trivy-owned concerns as well (deduplicated), or cap
  per concern, and add a not-observable finding saying results were dropped.

### B8 (Medium). Backup plan rules beyond 10 are dropped from the summary without notice
- **Repro:** F06-D-01, F06-D-02 and F10-B-11. The 11th rule (the only copy,
  kept 1 day) is invisible.
- **Code:** `backend/lambdas/rule_engine/resource_summary.py:322`.
- **Suggested fix:** add `rules_total` and `rules_truncated` to the entry,
  plus a sentence in `COVERAGE_NOTE`.

### B9 (Medium). Display-name truncation makes two resources indistinguishable
- **Repro:** F09-D-05. `customer_records_archive_primary_region_a` and `_b`
  both display as `customer_records_archive_primar…`, so the public-bucket
  finding can't say which.
- **Code:** `backend/shared/terraform_scope.py:43-44`.
- **Suggested fix:** when truncating, keep about 24 characters plus a short
  deterministic hash of the full key (e.g. `…_3f9a`). That is still
  identifier-only, so no free text gets through.

### B10 (Medium). Any Condition, even an irrelevant one, clears a public bucket policy
- **Repro:** F02-D-06. Principal `"*"` with only `aws:SecureTransport = true`
  is not flagged, though anyone on the internet can read over HTTPS.
- **Code:** `backend/lambdas/rule_engine/handler.py:283` (`and not s.get("Condition")`).
- **Suggested fix:** treat only identity- or network-restricting keys
  (`aws:SourceVpce`, `aws:SourceVpc`, `aws:SourceIp`, `aws:PrincipalOrgID`,
  `aws:PrincipalAccount`, `aws:PrincipalArn`, `aws:SourceArn`/`SourceAccount`)
  as restricting.

### B11 (Medium). Allow with NotAction or NotResource is never flagged
- **Repro:** F02-D-10 and F02-D-12. "Everything except iam:* and
  organizations:*" on `*`, and `s3:*` on every bucket but one, are both silent.
- **Code:** `backend/lambdas/rule_engine/handler.py:566-578` reads only
  `Action` and `Resource`.
- **Suggested fix:** an Allow with NotAction on Resource `*` is a broad grant.
  An Allow with NotResource (and no Resource) covers everything else.

### B12 (Medium). Permissions boundaries are ignored, so a bounded role is described as account-wide
- **Repro:** F02-D-13. `bounded_worker` (AdministratorAccess, capped by a
  boundary allowing one `s3:GetObject`) gets "...gets these permissions
  across the whole account".
- **Code:** `backend/lambdas/rule_engine/handler.py:725-772`.
- **Suggested fix:** when `permissions_boundary` is set, say so and drop the
  "whole account" claim (or evaluate the boundary when it resolves).

### B13 (Medium). An unattached open security group is called "reachable from the entire internet"
- **Repro:** F04-D-06. `orphan_any` (5432 from 0.0.0.0/0, attached to nothing),
  in both modes, since the database-port rule is ArchiBrief's own.
- **Code:** `backend/lambdas/rule_engine/handler.py:401` (risk text).
- **Suggested fix:** check whether any resource references the group
  (`vpc_security_group_ids`, `security_groups`, ENIs, load balancers). When
  none does, say the port would be open to the internet if the group were
  attached. Even when attached, prefer "open to" over "reachable from",
  since routes and listeners aren't checked.

### B14 (Low). Rules mode treats a conditional `count` as created
- **Repro:** F01-D-08 (rules mode only; Trivy evaluates it). `count = var.enable_debug_sg ? 1 : 0`
  with default `false` still yields a definite SSH finding.
- **Code:** `backend/lambdas/rule_engine/hcl_eval.py:130-143`.
- **Suggested fix:** evaluate a simple `cond ? a : b` when the condition
  resolves; otherwise mark copies as unknown and hedge the finding.

### B15 (Medium). A public bucket policy written as a policy document is missed
- **Repro:** post-freeze probe 1 (`test_post_freeze_probes.py`): `principals { type = "*", identifiers = ["*"] }`
  gives no "allows anyone" finding.
- **Code:** `hcl_eval.py:96-103` renders `{"*": ["*"]}`, which
  `handler.py:263-269` `_is_public_principal` doesn't recognise.
- **Suggested fix:** render `type = "*"` as `Principal: "*"`. Fix it together
  with B1.

### B16 (Medium). The ingest rejection reason echoes submitted file content and the server's temp path
- **Repro:** post-freeze probes 2 and 3. `failed to parse /tmp/…/main.tf: Unexpected token Token('STRING_CHARS', '` SYNTHETIC_SECRET_LINE_0005\n}\n\n')…`
  followed by the parser's whole expected-token list.
- **Code:** `backend/lambdas/ingest/handler.py:85-86` (the reason embeds
  `exc`) and `:229-230` (logged, then returned as Step Functions task output).
  The user-facing failure text is fixed, so this reaches CloudWatch and
  execution history, not the page.
- **Impact:** contradicts the module docstring ("Never logs the brief, file
  contents"). A secret near a syntax error ends up in logs and execution
  history.
- **Suggested fix:** build the reason from the error's line and column and the
  archive-relative path only.

### B17 (Low). The summary shows unset log retention as "not set (default: 0)"
- **Repro:** F08-D-03. Zero means never expire, but reads as zero days.
- **Code:** `backend/lambdas/rule_engine/resource_summary.py:190`.
- **Suggested fix:** show `"not set (default: never expires)"`.

### B18 (Medium). Trivy results for module-called resources are attributed to a phantom resource
- **Repro:** F01-dangerous in Trivy mode, found while explaining F01-D-07.
  Trivy correctly resolves `module.edge_lab`'s `open_admin = true` and reports
  AWS-0107 with `Resource = "module.edge_lab"`. That becomes "Security group
  'modules/edge/edge_lab' allows SSH or RDP from anywhere" with
  `resource "module" "…"`. Neither name exists, and the diagram can't place it.
- **Code:** `backend/lambdas/scan/handler.py:157-163`.
- **Suggested fix:** when the cause address is only `module.<call>`, use the
  check's resource type and the module's own resource, from Trivy's
  `CauseMetadata` occurrences or the file and line, or keep the module call
  name and say it's module-scoped.

### B19 (Low). Neutralization also rewrites provider sources
- **Repro:** running `neutralize_remote_sources` on F01-dangerous rewrites
  `required_providers { aws = { source = "hashicorp/aws" } }` in `versions.tf`.
- **Code:** `backend/lambdas/scan/handler.py:46` (any `source =` line).
- **Impact:** the scanned configuration differs from the submission. Low
  today, since Trivy downloads no providers.
- **Suggested fix:** limit rewriting to `module` block sources (as for B6).

### B20 (Low). A finding whose diagram node was cut off is shown as account-wide
- **Repro:** F10-G-61. The open-SSH group's node is past the 60-node cap, so
  its finding moves to `account_findings`. The diagram does say it was
  truncated, but the finding reads as account-wide.
- **Code:** `backend/shared/architecture_links.py` (`_place` → unplaced).
- **Suggested fix:** list it under "resources not drawn", not "account-wide".

## Coverage gaps (documented, not regressions)

No rule or summary setting exists for these, so they're counted separately:
- **F04-D-07:** a "private" subnet routed to an internet gateway.
- **F05-D-02/03 and F05-C-01/02:** AZ placement and provider Region aren't
  in the summary, so three replicas in one AZ, or a "dr" provider in the same
  Region, are invisible to the model.
- **F06-D-03 and F06-I-01:** what a backup selection protects.
- **F07-D-03/04/05:** a function URL or API method with authorization `NONE`
  as a paid entry path, and the diagram's internet edge to it.
- **F08-D-01/02 and F08-I-01:** S3 lifecycle and DynamoDB TTL.

Families 5 to 8 mostly test what the **model** would conclude. With these
gaps, the model can't be right about them from the summary alone, which is
worth fixing before the paid run.

## Observations (not scored)

- `parsed/{review_id}.json` keeps raw attribute values, including the
  synthetic `password` and `API_TOKEN` (F09). They never reached findings,
  the summary, the diagram or the report (F09-D-07 passed), but the parsed
  copy in S3 holds them for as long as its lifecycle allows.
- Instruction text in descriptions, tags, heredoc `user_data`, comments and
  the brief reached no deterministic output, and the findings matched the
  control exactly (F09-D-06 and F09-D-10, both modes). Guardrails, which
  checks the brief, wasn't exercised (it's an AWS call).

## Limitations and blocked checks

- **NOT RUN:** the model evaluation (`model_eval/`), Guardrails, AgentCore,
  Validate's rejection of model findings, chat, and the deployed Step
  Functions flow. Stubbed or fixture model output was not used for any
  metric here.
- No network monitor: "zero network fetching" rests on the dead proxy, the
  `.invalid` hosts and a successful offline scan, not on packet capture.
- Trivy 0.76.0 on Windows. CI and the Lambda run Linux. Results matched the
  existing trap suite (60/60), but Trivy's file ordering on Linux could move
  where the 200-result cap falls (B7 holds either way).
- Terraform behaviour is pinned from documentation, not from `terraform plan`
  (no providers downloaded). The AWS facts were checked against AWS docs on
  2026-10-20.
- In this worktree, 4 corpus-eval tests in the existing suite skip because
  `backend/corpus/data/` is gitignored. The other 710 pass.
- Some probes are string matches on finding text. F02-D-15 shows how that
  can misfire, which is why there is an adjudication column.

## Files

New, all under `tests/backend/adversarial/`, uncommitted: `README.md`,
`RESULTS.md`, `answer_key.json`, `FROZEN.sha256`, `harness.py`,
`conftest.py`, `__init__.py`, `test_adversarial_families.py`,
`test_evidence_overflow.py`, `test_post_freeze_probes.py`,
`run_adversarial.py`, `fixtures/` (9 families, 26 variants),
`model_eval/SCORING.md`, `model_eval/inputs/*.json` (26), and
`results/results.json` and `results/results_table.md`. No application code
changed.

## After fixes, 2026-10-22

All B1-B20 were independently confirmed and addressed on
`mobile-laptop/fix/adversarial-bugs`, worktree `archibrief-adversarial-fixes`.
Code ends at `320ffeb`. No push, merge, deployment, AWS call, model call or
Terraform command was made. The frozen answer key and hash are unchanged.

| Check | Original baseline | After fixes |
|---|---:|---:|
| Existing backend, including traps | 710 passed / 4 skipped | 776 passed / 4 skipped |
| Adversarial pytest, both modes including boundaries and post-freeze probes | 154 passed / 81 failed | 217 passed / 18 failed |
| Families 1-9, rules raw | 64 pass / 38 fail | 93 pass / 9 fail |
| Families 1-9, offline Trivy raw | 65 pass / 37 fail | 93 pass / 9 fail |
| Previously passing raw checks that regressed | n/a | 0 |
| Non-coverage frozen checks still failing | n/a | 0 |

Category counts below use the adjudicated denominator and are identical
in both modes after fixes. Acceptable-either-way checks are recorded,
not credited as defect detection.

| Category | Before rules | Before Trivy | After rules | After Trivy |
|---|---:|---:|---:|---:|
| Rule-covered recall | 16/24 | 16/24 | 24/24 | 24/24 |
| False claims avoided | 25/29 | 25/29 | 29/29 | 29/29 |
| Attribution | 4/6 | 4/6 | 6/6 | 6/6 |
| Uncertainty disclosed | 1/8 | 2/8 | 8/8 | 8/8 |
| Other evidence handling | 13/20 | 13/20 | 20/20 | 20/20 |
| Coverage-gap expectations | 0/13 | 0/13 | 0/13 | 0/13 |
| Acceptable either way | 2/2 | 2/2 | 2/2 | 2/2 |

These are fixture results, not recall on arbitrary Terraform or model-quality
measurements. Four of the coverage probes still pass raw because they only
find empty summary entries; adjudication retains the four failures.

### Remaining failures and limits

The 18 pytest failures are nine `coverage_gap` checks in each mode:
F04-D-07 (route-table reachability); F05-D-02/03 and F05-C-01/02
(AZ/Region placement); F07-D-03/04/05 (public function URLs, unauthenticated
API paths and the corresponding graph edge); F08-D-02 (DynamoDB TTL).
The four weak passing probes are F06-D-03/F06-I-01 (backup selections)
and F08-D-01/F08-I-01 (lifecycle settings). None is skipped or marked xfail.
These are additional coverage features, not unresolved B1-B20 checks.

Local module evaluation supports explicit singleton calls, literal/selected
inputs and the bounded resolver's expressions. Non-singleton/unknown
cardinality, missing/remote modules, module outputs, unsupported expressions
and provider inheritance are not a full Terraform evaluation. Unsupported
calls/inputs/providers receive coverage notices; unknown parent inputs never
fall back to child defaults. Rootless multi-directory archives are explicitly
independent static slices. Child scanner evidence is not mistaken for root
or instantiated-module evidence; own rules run instead, with a disclosure.

The four pre-existing backend skips need the gitignored local corpus data
(`tests/backend/corpus/test_eval*.py`). No skip was added for a fix.
Frontend wording was checked with the existing Prettier installation;
the frontend build/browser suite and Linux deployment package were not run.

### Evidence, review and paid work

Baseline artifacts are preserved as
`results/baseline-2026-10-20-results.json` and
`results/baseline-2026-10-20-results_table.md`, also at commit `16438e8`.
Current artifacts are `results/results.json` and `results/results_table.md`.
`run_adversarial.py` regenerated all 26 `model_eval/inputs/*.json`; each is
still explicitly **NOT RUN**. The original wrong-reason/vacuous IMDS and
principal passes now have direct positive controls and updated verification
notes. Notes cannot turn a failing raw check into a pass.

Code and security reviewers inspected the complete branch diff and used
focused repros. Their scanner attribution, source identity, unknown-input,
Unicode escape, packaging and effective-byte-budget findings were addressed
with regression tests. Both reported no remaining concrete blocker in their
reviewed corrections. This is local source/test evidence, not certification
of the deployed system.

Still requires a separately authorized paid evaluation: the 26 reasoning
inputs, Guardrails, Validate's treatment of real model output, retrieval and
citation semantic support, report chat, AgentCore and the deployed workflow.
Commands, dispositions, test paths and commits: [FIX_REPORT.md](FIX_REPORT.md).
