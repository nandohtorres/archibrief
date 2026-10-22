# Adversarial Terraform families

Ten families of adversarial Terraform, each tested against ArchiBrief's real
deterministic path: archive extraction, HCL parse, the offline Trivy scan,
the rules, the resource summary, the architecture diagram and the report
build. The point is to find where the system claims more, or less, than the
code shows. A family passes because the system stays truthful, not because
it produces more findings. "This can't be determined from the code" is a
valid outcome.

Results and the bug report: [RESULTS.md](RESULTS.md). The model evaluation
inputs are prepared but **NOT RUN**: [model_eval/SCORING.md](model_eval/SCORING.md).

## What's here

| Path | What it is |
|---|---|
| `fixtures/<family>/<variant>/` | Terraform per variant: `dangerous`, `corrected` (or `control`), `incomplete` |
| `answer_key.json` | The frozen expectations: must detect, must not claim, must disclose, acceptable uncertainty, the affected resource, and exact `file:line` evidence |
| `FROZEN.sha256` | SHA-256 of `answer_key.json`; the suite refuses to run if they differ |
| `harness.py` | Packs a fixture into a tar and runs it through the real path; the probes and the verdict rules |
| `test_adversarial_families.py` | Families 1-9, one test per check and mode |
| `test_evidence_overflow.py` | Family 10: every bound, one below, at and one above |
| `test_post_freeze_probes.py` | Probes written after the frozen run to explain individual results; not scored |
| `run_adversarial.py` | Writes `results/results.json`, `results/results_table.md` and `model_eval/inputs/` |

Family 10's cases are generated from the code's constants at test time,
which the suite first checks against the frozen values. Families 1-9 use
the static fixtures.

## Freeze record

`answer_key.json` was written and frozen before any rule, summary or
diagram output was inspected (only a parse check ran, to confirm the
fixtures are valid HCL). SHA-256 `577c434392ef0f4ea559098c3c18a4921c629d9fd3e7e0b582a9d7a455ee6fe9`,
2026-10-20T20:20:19Z. It hasn't been edited since. Where a frozen probe
turned out to be wrong, or right for the wrong reason, the raw verdict
stands and `run_adversarial.py` records an adjudication note next to it
(RESULTS.md, "Adjudication").

## Reproduce

From the repository root, with the existing backend venv and an offline
Trivy 0.76.0 (the version CI pins):

```bash
export TRIVY_PATH=/path/to/trivy          # optional: without it the trivy-mode tests skip
python -m pytest tests/backend/adversarial -q -p no:cacheprovider
python -m pytest tests/backend/adversarial -q -m "not coverage_gap"   # leave out documented gaps
python -m tests.backend.adversarial.run_adversarial                    # results/ and model_eval/inputs/
python -m pytest tests/backend/traps -q                                # existing regression traps
```

Failing tests are the findings. None is marked xfail or skipped to make the
run look clean. The original baseline had 81 failures; after B1-B20 fixes,
18 remain, all declared coverage gaps. See RESULTS.md and FIX_REPORT.md.

## Safety

- No AWS calls, no model calls, no `terraform init/plan/apply`, and no
  provider downloads. Provider semantics are pinned in each fixture's header
  comment and checked against the docs below.
- Trivy runs through the scanner's own `run_trivy`: `--skip-check-update`,
  a clean environment, and HTTP(S) proxies pointed at a closed port.
- Every remote module source uses the reserved `.invalid` TLD. B6's
  original one-line-source bypass is fixed by structural neutralization;
  the scanner still runs offline in its existing isolation.
- Instruction text and secret markers are inert synthetic strings
  (`SYNTHETIC-SECRET-DO-NOT-LEAK-*`).
- Scanner failures are simulated by patching `subprocess.run`; no
  submitted file is ever executed.

## Semantics, checked against official documentation (2026-10-20)

- Variable precedence: `*.auto.tfvars` and `terraform.tfvars` override a
  variable's `default`. [HashiCorp: input variables](https://developer.hashicorp.com/terraform/language/values/variables)
- A child module is part of the configuration only if a `module` block calls it. [HashiCorp: modules](https://developer.hashicorp.com/terraform/language/modules)
- IMDS precedence: launch values override account defaults; account
  defaults are per Region. [EC2: order of precedence](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html),
  [EC2: new instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html)
- `aws_ec2_instance_metadata_defaults` applies to its provider's Region (or
  its `region` argument); `http_tokens` takes `optional`, `required` or
  `no-preference`. [provider docs](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/ec2_instance_metadata_defaults.html.markdown)
- `aws_iam_policy_document` statements carry `condition`, `not_actions`,
  `not_resources` and `not_principals`. [provider docs](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/d/iam_policy_document.html.markdown)
- S3 lifecycle Expiration on a versioned bucket only adds a delete marker;
  noncurrent versions need NoncurrentVersionExpiration; removal can lag. [S3: expiring objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html)
- DynamoDB TTL deletes expired items "typically within a few days". [DynamoDB: TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)
- AWS Budgets notifies; data updates up to three times a day and spend
  can exceed the threshold before notification. [Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
