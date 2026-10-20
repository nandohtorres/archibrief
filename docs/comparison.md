# Local Trivy versus saved ArchiBrief reviews

Measured 2026-10-16 against the archives committed at `8d391b0`. This compares
static scanner output with historical saved reviews of the same source slices,
not two fresh production executions or a benchmark of general accuracy.

## Method and evidence

[`evidence/compare_demos.py`](evidence/compare_demos.py) extracts each archive
into an ignored scratch directory, neutralizes external module sources using
the existing scanner code, and calls `run_trivy`. No Terraform or AWS commands
run. The originals are unchanged; archive SHA-256 values are recorded in
[`summary.json`](evidence/trivy/summary.json). Run from the repo root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
..\archibrief\backend\.venv\Scripts\python.exe docs/evidence/compare_demos.py
```

The installed Trivy is **0.76.0**, matching the version recorded for the saved
reviews in [demos.md](demos.md). It ran `config --skip-check-update
--skip-version-check --disable-telemetry --misconfig-scanners terraform
--format json --quiet --exit-code 0`, with a fresh cache and dead HTTP proxies
through `backend/lambdas/scan/handler.py`. This uses bundled checks offline;
the installed-cache metadata from `trivy --version` is recorded separately and
does not establish that its cached check bundle was used by the fresh-cache scan.
Remote-source attributes neutralized: breach 1, Medicare 5, FEC 0. The scanner
cannot review modules absent from the archive.

Full local outputs: [breach](evidence/trivy/breach-pattern.json),
[Medicare](evidence/trivy/medicare-platform.json),
[FEC](evidence/trivy/fec-database.json). Counts include all severities and count
each failing check/resource occurrence, including counted resource instances.

## Results

| Archive | Terraform files | Trivy failures (critical/high/medium/low) | Failures whose ID is in ArchiBrief's trusted set | Saved ArchiBrief findings (rule/model) |
|---|---:|---|---:|---|
| breach-pattern | 8 | 16 (2/6/2/6) | 5 | 12 (6/6), committed JSON |
| medicare-platform | 31 | 7 (2/4/0/1) | 4 | 9 (2/7), committed JSON |
| fec-database | 1 | 23 (1/11/1/10) | 8 | 14 (6/8), committed JSON (re-run 2026-10-16) |

Local counts and types come from `evidence/trivy/summary.json`; saved counts
come from the three `frontend/public/demos/reports/*.json` files. The FEC report
is the 2026-10-16 re-run (`b7f2a3e7`); the first run was held back over a false
instance count (see [demos.md](demos.md)).

The trusted-set column is an ID membership count, not a prediction of final
rule findings: ArchiBrief filters, maps and groups scanner output, then adds
custom rules. Trivy reports AWS-0094 alongside related access-block failures;
ArchiBrief keeps selected check IDs and groups concerns per resource. Final
report counts use a different unit.

## Breach pattern

Trivy flags IMDS tokens (AWS-0028), EBS encryption (AWS-0131), bucket access
blocks (AWS-0086/0087/0091/0093/0094), logging (AWS-0089), versioning
(AWS-0090), unrestricted egress (AWS-0104), missing rule descriptions
(AWS-0124), and flow logs (AWS-0178). The exact counts/resources are in the raw
JSON and summary's `check_ids`.

The saved ArchiBrief rules cover bucket encryption, absent CloudTrail in the
slice, the compute role's broad S3 policy, IMDS, bucket access blocking and
versioning. Its model connects proxy exposure, IMDSv1 and broad permissions to
the workload's cardholder-data risk; it also discusses TLS and availability.
That workload-specific explanation is the added capability. It introduces new
error opportunities: the manual audit calls the chain citation weak and the
same-region data-transfer cost claim wrong. More narrative findings do not
establish better accuracy than Trivy.

## Medicare platform

Trivy's seven failures are the bucket-access-block check family and two
unrestricted egress rules. The saved ArchiBrief report groups access-block
findings and adds absent CloudTrail for the submitted slice. Its model also
recognizes configured key rotation, WAF allowlists/logging and bucket controls,
and evaluates uncertainty against the brief's health-data requirements.

The model's backup-visibility statement is incomplete: the reviewed code does
declare schedules and retention. `docs/demos.md` records the resource-summary
gap and subsequent fix; this saved output predates a confirming rerun. Neither
tool can establish that omitted organization-wide controls are absent in CMS's
actual accounts.

## FEC database

Trivy flags three unencrypted cluster declarations (AWS-0079), seven public
cluster instances (AWS-0180), seven Performance Insights omissions (AWS-0133),
open SSH/RDP ingress (AWS-0107), unrestricted egress (AWS-0104), missing group
or rule descriptions (AWS-0099/0124), and flow logs (AWS-0178).

ArchiBrief's rules report the public database instances, all-port ingress
(including database ports and SSH/RDP) and absent CloudTrail. The first saved
run's model claimed one instance per cluster and no read replicas, though the
Terraform sets counts of 3/2/2; the resource summary didn't carry counts. After
that fix, the 2026-10-16 re-run describes production as one writer and two
readers, and adds what Trivy doesn't frame for this workload: IAM database
authentication off against a stated traceability requirement, no log export,
static reader capacity for filing-deadline spikes, and a two-AZ subnet group.
The hand check found one wrong model finding (`copy_tags_to_snapshot` called
unconfirmed; every cluster sets it), which led to another summary fix. This is
why a report needs code-grounded review even when citations resolve.

## What this comparison supports

ArchiBrief already embeds Trivy; it is not an independent competitor baseline.
Trivy contributes repeatable static detections. ArchiBrief selects/group checks,
adds custom rules, and explains risk using a workload brief and AWS guidance.
This sample demonstrates that combination and its failure modes, rather than
a numeric precision/recall advantage. Check selection, historical prompts,
missing modules and report grouping prevent a fair
single-score ranking.
