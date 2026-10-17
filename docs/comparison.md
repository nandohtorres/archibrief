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
| fec-database | 1 | 23 (1/11/1/10) | 8 | 10 (6/4), historical documentation only |

Local counts and types come from `evidence/trivy/summary.json`; saved counts
come from the two `frontend/public/demos/reports/*.json` files. FEC's count is
from `docs/demos.md`'s run table. **There is no committed FEC report JSON in
this checkout**, so its comparison below is limited to that document's manual
audit. It is marked unpublished there, pending a rerun. No replacement report
was fabricated or fetched from AWS.

The trusted-set column is an ID membership count, not a prediction of final
rule findings: ArchiBrief filters, maps and groups scanner output, then adds
custom rules. In particular, the S3 missing-access-block check AWS-0094 is
expanded into related Trivy failures; final report counts use a different unit.

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

The historical ArchiBrief audit identifies public database instances,
all-port ingress, and absent CloudTrail. Its model incorrectly says the clusters
have a single instance and no read replicas: Terraform specifies counts of
3/2/2. This is why a report needs code-grounded review even when citations
resolve. The raw local scanner correctly enumerates those seven instances;
the documented summary/count fixes need a new saved run before claiming the
ArchiBrief model now describes this example correctly.

## What this comparison supports

ArchiBrief already embeds Trivy; it is not an independent competitor baseline.
Trivy contributes repeatable static detections. ArchiBrief selects/group checks,
adds custom rules, and explains risk using a workload brief and AWS guidance.
This sample demonstrates that combination and its failure modes, rather than
a numeric precision/recall advantage. Check selection, historical prompts,
missing modules, report grouping and the missing FEC artifact prevent a fair
single-score ranking.
