# Demo reviews

ArchiBrief's public demos are real reviews of real, public Terraform.
Each was run once, by the site owner, through the deployed pipeline, and
saved. Visitors open the saved report: visiting never starts a paid
review (ADR-0029).

Everything a demo needs lives in `frontend/public/demos/`:

| File | What it is |
|---|---|
| `<id>.tar` | The reviewed `.tf` files, unchanged, plus `SOURCE.md` (repository, commit, license) and the project's license file |
| `demos.json` | Title, source link pinned to the commit, license, disclaimer and the workload brief for each demo |
| `reports/<id>.json` | The saved report, exactly as `GET /reviews/{id}` returned it |

`scripts/build_demo_archives.py` rebuilds the archives from the pinned
commits; `--check` fails if a rebuilt archive differs from the committed
one.

## The demos

### 1. The 2019 bank breach pattern (`breach-pattern`)

- **Source:** Rhino Security Labs, CloudGoat scenario `cloud_breach_s3`,
  commit `63c65bd26edc6919499adfa20b176c450e35c33c`. BSD-3-Clause.
- **What it is:** a security firm's vulnerable-by-design AWS lab. Its
  attack path matches the one publicly reported for the 2019 Capital One
  breach: a misconfigured reverse proxy on EC2, the instance metadata
  service (IMDSv1) handing out the role's credentials, a role with
  `AmazonS3FullAccess`, and data copied out of S3. **It is not Capital
  One's code**, and the site says so.
- **Size:** 8 files, 15 resources.
- **Baseline answers sent with the brief:** PCI-DSS, US only; moderate,
  single-region; customer-facing, 99.9%.

### 2. Medicare data APIs platform (`medicare-platform`)

- **Source:** Centers for Medicare & Medicaid Services, `CMSgov/cdap`,
  commit `e3b284998d05d77660f6a734a11aa2b42de1f205`. CC0-1.0.
- **What it is:** CMS's shared platform for the AB2D, BCDA and DPC
  Medicare claims-data APIs. The reviewed slice is the network, web
  firewall, encryption keys, backups and access logs
  (`terraform/services/{020-vpc-network,security-groups,api-waf,kms-keys,backup-plan,bucket-access-logs}`
  plus the local modules they call). A shared module pulled from another
  repository isn't included.
- **Size:** 31 files, 30 resources.
- **Baseline answers:** HIPAA and FISMA, data stays in the US; moderate
  partner traffic from allowlisted IPs; 99.9%, not life-critical.

### 3. Federal Election Commission databases (`fec-database`)

- **Source:** `fecgov/fec-infrastructure`, commit
  `bd6fbd5ca00e3927b0d2ce0fd543ec9395315edd`. US Government work,
  public domain in the US. Last changed in 2020; may not match what
  runs today.
- **What it is:** Aurora PostgreSQL clusters for production, staging and
  development (3, 2 and 2 instances), their network and security group.
- **Size:** 1 file, 18 resources.
- **Baseline answers:** public-record data with integrity requirements,
  US only; heavy reads around filing deadlines; production important,
  staging and development best effort.

## How each report was produced

All runs: 2026-10-15, through `https://api.archibrief.dev` (admin
path), rule version `rule_engine@2026-10-15b` with Trivy 0.76.0, model
`us.anthropic.claude-sonnet-4-6`, prompt `reason_prompt@2026-10-15d`,
corpus v3.

| Demo | Review ID | Duration | Findings | Status |
|---|---|---|---|---|
| breach-pattern | `cd4b6384-30cb-48c9-a779-714b7cb7194e` | 83s | 12 (6 rule, 6 model) | saved |
| medicare-platform | `8d46136d-e14f-4010-aaa4-e2bf0408b06d` | 80s | 9 (2 rule, 7 model) | saved |
| fec-database | `25ca09c8-4f2f-4be8-81be-b8c1e5c4bb02` | 63s | 10 (6 rule, 4 model) | **not published**: one false "fact" (below); re-run pending |

The briefs are written by ArchiBrief from each project's public README.
The projects' owners did not write them or review these results.

## Every finding, checked against the code

Each model finding was checked by hand against the reviewed Terraform.
Rule findings are deterministic and were checked the same way.

Findings marked wrong, overstated, incomplete or weakly cited carry a
visible reviewer note on the site: `reviewerNotes` in
`frontend/public/demos/demos.json`, kept apart from the saved reports so
those stay the pipeline's unedited output.

### breach-pattern

| Finding | Verdict |
|---|---|
| Rule: no server-side encryption on `cg-cardholder-data-bucket` | Correct |
| Rule: no `aws_cloudtrail` | Correct |
| Rule: role `cg-banking-WAF-Role` is used by running code and has `AmazonS3FullAccess` | Correct (`managed_policy_arns`, EC2 trust) |
| Rule: proxy instance doesn't require IMDSv2; risk text names the broad role | Correct (no `metadata_options`) |
| Rule: bucket public access not fully blocked | Correct |
| Rule: bucket versioning off | Correct |
| Model: the proxy, broad role and IMDSv1 form a complete SSRF-to-S3 chain | Correct, and the key finding. **Its citation is weak**: the quoted text is about traffic staying on the AWS network, not about credential theft |
| Model: no S3 VPC endpoint; bucket traffic goes over the public internet | Endpoint: correct. "Public internet" overstates it: the traffic uses S3's public endpoints but stays on AWS's network |
| Model: proxy accepts HTTP on port 80 only, no TLS | Correct (security group allows 80 only) |
| Model: single EC2 instance, no load balancer or Auto Scaling, can't meet 99.9% | Correct |
| Model: S3 traffic through the internet gateway incurs avoidable data-transfer charges | **Wrong**: S3-to-EC2 transfer in the same region is free, and there is no NAT gateway |
| Model: detailed monitoring off on the proxy | Correct (`monitoring` unset; default false) |

### medicare-platform

| Finding | Verdict |
|---|---|
| Rule: no `aws_cloudtrail` in the slice | Correct for the slice; CloudTrail may live elsewhere in CMS's accounts |
| Rule: access-log bucket has no public access block | Correct for the slice (it has a bucket policy only) |
| Model: both KMS keys rotate automatically | Correct |
| Model: WAF with IPv4/IPv6 allowlists and logging | Correct |
| Model: access-log bucket has versioning, object lock, lifecycle and encryption | Correct |
| Model: encryption is on but whether it uses the customer-managed key isn't confirmed | Fair; the summary doesn't carry that setting |
| Model: no IAM/STS shown for partner access | Fair for this slice |
| Model: backup schedule, retention and copies "aren't visible" | **Incomplete**: the code sets four rules (every 4 hours kept 1 day and copied to a second vault; daily kept 7; weekly kept 35; monthly kept 90). The resource summary didn't include backup plans; it does now (bug 5) |
| Model: WAF logging and Datadog monitoring present, no further alerting shown | Fair |

### fec-database (not published)

| Finding | Verdict |
|---|---|
| Rule: security group `rds` allows 0.0.0.0/0 to database ports | Correct (all ports, all protocols) |
| Rule: security group `rds` allows SSH or RDP from anywhere | Correct (all ports) |
| Rule: production, staging and development instances publicly accessible | Correct |
| Rule: no `aws_cloudtrail` | Correct |
| Model: "only a single cluster instance is provisioned per Aurora cluster" | **Wrong**: `count = 3`, `2`, `2`. The summary didn't carry counts; fixed in `ec537fe` (`copies`) |
| Model: no read replicas or caching for deadline spikes | Wrong for the same reason (the extra instances are readers) |
| Model: no RDS event subscriptions | Correct |
| Model: Aurora backtracking not configured | Correct |

## Bugs the demos found (all fixed)

See the Issues Log entry of 2026-10-15 for detail.

1. No rule for broad managed policies on compute roles; IMDSv1 only
   caught by Trivy (`d72c0ea`).
2. Trivy results for `count`/`for_each` resources were dropped
   (`cd396d2`).
3. rule_engine timed out building the HCL parser for `jsonencode()`
   policies at 256 MB (`ec537fe`, now 1024 MB / 30s).
4. Resource counts weren't in the summary, so the model invented them
   (`ec537fe`).
5. Backup plans weren't in the resource summary, so the model couldn't
   see schedules or retention. Each rule's schedule, retention, cold
   storage, copy and continuous-backup setting is now stated; rule names
   are free text and left out.

## Talking points for showing it

- **Breach pattern:** the rules catch each misconfiguration
  deterministically, and the IMDS finding names the broad role, so the
  chain is stated even without the model. The model then explains the
  whole chain in business terms (PCI scope, cardholder data).
- **Medicare:** a well-built platform gets a mostly clean, specific
  report instead of noise; the honest gaps (backup retention it couldn't
  see) show what "only claims what the code shows" means.
- **FEC:** three public databases open on every port, found on public
  government code.
- **Verification:** every finding above was checked by hand, including
  the ones the model got wrong. That check is what found four of the
  five bugs.
