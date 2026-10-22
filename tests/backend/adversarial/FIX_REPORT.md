# Adversarial fixes: local handoff, 2026-10-22

All B1-B20 were confirmed and addressed. All frozen non-coverage checks
pass in rules and offline Trivy modes; no previously passing raw check
regressed. The complete adversarial suite still fails on documented
coverage gaps. No frozen expectation was changed, weakened, xfailed or skipped.

Worktree: `C:/Users/ferna/cursor projects/side-projects/archibrief-adversarial-fixes`.
Branch: `mobile-laptop/fix/adversarial-bugs`. Baseline suite committed at
`16438e8`; implementation ends at `320ffeb`. Everything is local, ready
for review and a separately requested push. No merge or deployment happened.

## Results

| Suite | Before | After |
|---|---:|---:|
| Backend, excluding adversarial, including all 60 trap tests | 710 passed / 4 skipped | 776 passed / 4 skipped |
| Full adversarial pytest | 154 passed / 81 failed | 217 passed / 18 failed |
| Rule-covered recall, each mode | 16/24 | 24/24 |
| False claims avoided, each mode | 25/29 | 29/29 |
| Attribution, adjudicated, each mode | 4/6 | 6/6 |
| Uncertainty, rules / Trivy | 1/8 / 2/8 | 8/8 / 8/8 |
| Other evidence handling, each mode | 13/20 | 20/20 |
| Coverage-gap expectations, adjudicated, each mode | 0/13 | 0/13 |

The four pre-existing skips are local-corpus availability checks. The
remaining 18 adversarial failures are nine coverage gaps in each mode;
four other weak coverage probes pass raw but remain adjudicated failures.
See RESULTS.md for exact IDs and the complete category table. These are
fixed fixture denominators, not general accuracy or live-model metrics.

Ruff passed on backend and changed Python tests/scripts. `git diff --check`
and Prettier on the changed UI component passed. No new dependency install,
venv, frontend build, browser run or Linux deployment test was performed.
The scan packaging specification is covered by transitive-import and
dependency regression tests; no deployment was attempted.

## Bug verdicts, commits and regression locations

All test paths below are relative to `tests/backend/`.

| Bug | Disposition and reason | Local commits | Regression paths |
|---|---|---|---|
| B1 | Preserve conditions and negative policy elements instead of changing equivalent policies' meanings. | `9665b72` | `lambdas/rule_engine/test_hcl_eval.py` |
| B2 | Scope metadata defaults to the provider/Region/module; explicit launch options override defaults. | `d334d0b` | `lambdas/rule_engine/test_metadata_defaults.py` |
| B3 | Apply automatic variable files in Terraform order; disclose unselected CLI variable-file scope. | `11456e6` | `lambdas/ingest/test_handler.py` |
| B4 | Evaluate explicit local singleton calls, bind inputs, exclude uncalled and disabled modules; disclose unsupported evaluation. | `320ffeb` | `lambdas/ingest/test_module_evaluation.py` |
| B5 | Parse module calls and surface missing/remote/unsupported scope in findings and summary. | `320ffeb` | `lambdas/ingest/test_module_evaluation.py`, `lambdas/ingest/test_handler.py` |
| B6 | Structural module-source neutralization, fail before scanning on unparseable HCL; include the parser in the scan package. | `fc9ed33`, `e57e377` | `lambdas/scan/test_handler.py`, `test_package_lambdas.py` |
| B7 | Preserve concern coverage at the scanner cap; disclose totals/truncation and use own-rule fallback. | `53e93cc` | `lambdas/scan/test_handler.py` |
| B8 | Disclose backup rule totals/truncation and preserve the decisive copy/short-retention rule across the bound. | `7786812` | `lambdas/rule_engine/test_resource_summary.py` |
| B9 | Stable scoped hash suffixes distinguish long/sanitized display names. | `da8034d` | `shared/test_terraform_scope.py`, `lambdas/rule_engine/test_architecture.py` |
| B10 | Only proven restrictive positive IAM conditions suppress public access; HTTPS-only, negated, wildcard and unknown conditions do not. | `bffe096` | `lambdas/rule_engine/test_policy_semantics.py` |
| B11 | Detect broad complement grants without inventing Resource wildcard evidence or calling exclusions full admin. | `bffe096`, `a54325f` | `lambdas/rule_engine/test_policy_semantics.py` |
| B12 | Acknowledge permissions boundaries and other effective-permission limits in broad-role warnings. | `bffe096` | `lambdas/rule_engine/test_policy_semantics.py` |
| B13 | Distinguish permissive security-group configuration from proven attachment/reachability. | `bffe096` | `lambdas/rule_engine/test_policy_semantics.py` |
| B14 | Resolve supported conditional counts; qualify unknown creation; unsupported HCL escapes remain unknown. | `b762ba6`, `320ffeb` | `lambdas/rule_engine/test_hcl_eval.py` |
| B15 | Recognize wildcard principals and provider set semantics for duplicate principal entries. | `9665b72`, `ace563d` | `lambdas/rule_engine/test_hcl_eval.py` |
| B16 | Return/log only trusted parser error categories and numeric locations, never source content or temporary paths. | `11456e6` | `lambdas/ingest/test_handler.py` |
| B17 | Report unset/zero log retention as never expiring. | `7786812` | `lambdas/rule_engine/test_resource_summary.py` |
| B18 | Preserve module-level attribution, nested indices and module-origin provenance; never fabricate a resource or accuse a same-named root resource. | `a54325f`, `320ffeb` | `lambdas/scan/test_handler.py`, `lambdas/ingest/test_module_evaluation.py`, `lambdas/rule_engine/test_architecture.py` |
| B19 | Rewrite actual module source attributes; preserve provider sources, comments and heredoc content. | `fc9ed33` | `lambdas/scan/test_handler.py` |
| B20 | Keep legacy account_findings transport but identify unplaced scope; stop attaching omitted declared resources to unrelated nodes. Correct UI description. | `c302172` | `lambdas/rule_engine/test_architecture.py` |

Code and security reviewers independently checked the full branch diff,
including subsequent corrections. Their concrete findings were reproduced
with failing tests before correction. Final focused rechecks found no
remaining concrete blocker in the reviewed changes.

## Intentional limits and remaining work

No B-number is left untreated, but B4 uses a supported static subset,
not a complete module interpreter. Singleton local calls are evaluated;
non-singleton/unknown counts and nonempty for_each, remote/missing/cyclic
modules, module outputs and unsupported expressions are disclosed instead.
Provider inheritance/mapping is explicitly unknown and cannot prove an
IMDS account-default scope. A rootless multi-directory archive is labeled
independent static slices, not one deployed architecture.

Module evaluation is bounded by 64 visits, depth checks, 1,000 resource/data
declarations and a 50 MiB aggregate work budget. Effective bound values and
recursive input-resolution allocations consume that budget. Over-budget
work produces notices. Trivy's child/module addresses cannot prove bound
input semantics, so own rules cover evaluated child resources even when
the scanner returns no hits; omitted scanner coverage is disclosed.

Additional coverage features are unchanged: route-table reachability,
AZ/Region placement, backup selections, public Lambda URL/API entry paths
and diagram edges, S3 lifecycle details and DynamoDB TTL. These are the
thirteen adjudicated coverage expectations, separate from B1-B20.

Paid/deployed evaluation remains **NOT RUN**: all 26 regenerated reasoning
inputs in `model_eval/inputs/`, Guardrails, Validate on real model output,
retrieval/citation semantic support, report chat, AgentCore and the deployed
Step Functions workflow. No model-quality or deployed-security claim follows
from the local tests. No Linux Trivy comparison or packet capture was run.

## Frozen probes and existing-test corrections

- `answer_key.json` SHA-256 remains
  `577c434392ef0f4ea559098c3c18a4921c629d9fd3e7e0b582a9d7a455ee6fe9`;
  `FROZEN.sha256` is unchanged.
- F01-D-05 uses a wrong uncalled-resource path; the additional module test
  checks actual exclusion. No frozen probe was edited.
- F02-D-05 now passes for the preserved restrictive condition; the separate
  anonymous policy-document probe detects the public twin.
- F03-D-04/05/06 are no longer vacuous: legacy_proxy and west_worker are
  detected while the protected instances remain unflagged and role links
  remain distinct.
- F02-D-15 originally matched generic recommendation text. The wording now
  says workload and never implies an unattached policy is held by a role.
- The injection-control comparison still passes, including coverage
  notice titles. Notices are consolidated with all details in evidence,
  instead of repeated indistinguishable titles per missing input/module.
- Four weak empty-summary coverage probes remain adjudicated failures.
  Verification notes never override a failing raw verdict with a pass.
- Existing ellipsis assertions were replaced with bounded/stable/distinct
  graph-name checks. A module-identity test now includes a real module call.
  The remote-module test now uses an actual module block. Recipe tests
  separately verify coverage notices (no citation/concern, evidence present)
  instead of demanding a priced remediation recipe for missing evidence.

## Reproduce locally

PowerShell, from the fix worktree. Use the existing venv; do not initialize
Terraform or call AWS. Choose fresh pytest basetemp suffixes for reruns.

```powershell
$jobTmp = Join-Path $env:TEMP 'archibrief-adversarial-recheck'
New-Item -ItemType Directory -Force -Path $jobTmp | Out-Null
$env:TMP = $jobTmp
$env:TEMP = $jobTmp
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TRIVY_PATH = (Get-Command trivy.exe).Source
$pythonExe = '..\archibrief\backend\.venv\Scripts\python.exe'
& $pythonExe -B -m pytest tests/backend --ignore=tests/backend/adversarial -q -p no:cacheprovider --basetemp "$jobTmp/backend"
& $pythonExe -B -m pytest tests/backend/adversarial -q -p no:cacheprovider --basetemp "$jobTmp/adversarial"
& $pythonExe -B -m tests.backend.adversarial.run_adversarial
Get-FileHash tests/backend/adversarial/answer_key.json -Algorithm SHA256
```

The full adversarial command intentionally returns nonzero for the 18
coverage-gap failures. Do not mark them skipped or change the frozen key.
The metrics command writes explicit review artifacts and prepared model
inputs, and never invokes a model. Offline Trivy always goes through the
existing scanner isolation and includes `--skip-check-update`.

Original results: `results/baseline-2026-10-20-results.json` and
`results/baseline-2026-10-20-results_table.md`; current results:
`results/results.json` and `results/results_table.md`. The original suite
and baseline also remain in commit `16438e8` and the original worktree.

## Files touched after preserving the baseline

57 files relative to the frozen baseline commit `16438e8`. The separate
baseline preservation commit contains the original suite, not fixes.

```text
backend/lambdas/ingest/handler.py
backend/lambdas/rule_engine/handler.py
backend/lambdas/rule_engine/hcl_eval.py
backend/lambdas/rule_engine/resource_summary.py
backend/lambdas/scan/handler.py
backend/shared/architecture_links.py
backend/shared/archive.py
backend/shared/hcl_eval.py
backend/shared/terraform_scope.py
frontend/components/architecture-view.tsx
scripts/package_lambdas.py
tests/backend/adversarial/FIX_REPORT.md
tests/backend/adversarial/README.md
tests/backend/adversarial/RESULTS.md
tests/backend/adversarial/REVIEW.md
tests/backend/adversarial/model_eval/inputs/F01-corrected.json
tests/backend/adversarial/model_eval/inputs/F01-dangerous.json
tests/backend/adversarial/model_eval/inputs/F01-incomplete.json
tests/backend/adversarial/model_eval/inputs/F02-corrected.json
tests/backend/adversarial/model_eval/inputs/F02-dangerous.json
tests/backend/adversarial/model_eval/inputs/F02-incomplete.json
tests/backend/adversarial/model_eval/inputs/F03-corrected.json
tests/backend/adversarial/model_eval/inputs/F03-dangerous.json
tests/backend/adversarial/model_eval/inputs/F03-incomplete.json
tests/backend/adversarial/model_eval/inputs/F04-corrected.json
tests/backend/adversarial/model_eval/inputs/F04-dangerous.json
tests/backend/adversarial/model_eval/inputs/F04-incomplete.json
tests/backend/adversarial/model_eval/inputs/F05-corrected.json
tests/backend/adversarial/model_eval/inputs/F05-dangerous.json
tests/backend/adversarial/model_eval/inputs/F05-incomplete.json
tests/backend/adversarial/model_eval/inputs/F06-corrected.json
tests/backend/adversarial/model_eval/inputs/F06-dangerous.json
tests/backend/adversarial/model_eval/inputs/F06-incomplete.json
tests/backend/adversarial/model_eval/inputs/F07-corrected.json
tests/backend/adversarial/model_eval/inputs/F07-dangerous.json
tests/backend/adversarial/model_eval/inputs/F07-incomplete.json
tests/backend/adversarial/model_eval/inputs/F08-corrected.json
tests/backend/adversarial/model_eval/inputs/F08-dangerous.json
tests/backend/adversarial/model_eval/inputs/F08-incomplete.json
tests/backend/adversarial/model_eval/inputs/F09-control.json
tests/backend/adversarial/model_eval/inputs/F09-dangerous.json
tests/backend/adversarial/results/baseline-2026-10-20-results.json
tests/backend/adversarial/results/baseline-2026-10-20-results_table.md
tests/backend/adversarial/results/results.json
tests/backend/adversarial/results/results_table.md
tests/backend/adversarial/run_adversarial.py
tests/backend/lambdas/ingest/test_handler.py
tests/backend/lambdas/ingest/test_module_evaluation.py
tests/backend/lambdas/rule_engine/test_architecture.py
tests/backend/lambdas/rule_engine/test_hcl_eval.py
tests/backend/lambdas/rule_engine/test_metadata_defaults.py
tests/backend/lambdas/rule_engine/test_policy_semantics.py
tests/backend/lambdas/rule_engine/test_resource_summary.py
tests/backend/lambdas/scan/test_handler.py
tests/backend/shared/stakeholder/test_catalog.py
tests/backend/shared/test_terraform_scope.py
tests/backend/test_package_lambdas.py
```
