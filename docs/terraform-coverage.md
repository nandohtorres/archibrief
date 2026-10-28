# Bounded Terraform configuration coverage

Observation version: `terraform-observations@2026-10-23`; rules:
`rule_engine@2026-10-23`. This describes local source, not a deployed release
or a measured model-quality improvement. The existing static HCL parser/resolver
is extended incrementally; Terraform, providers and submitted code never run.

Only AWS provider Region configuration is retained, never credentials. Local
singleton calls preserve default inheritance and explicit provider mappings.
Resource Region overrides are separate from provider configuration. Actual
account identity stays unknown. Aliases do not prove Regions or accounts.
Observations carry stable scoped identity, analysis version, inspected setting,
typed scalar state, direct relationships and source module. Unrecorded source
line numbers stay null. Known configuration is distinct from inspected absence,
unknown and unsupported expressions; creation can be conditional.

| Domain | Supported slice | Limits |
|---|---|---|
| Placement | Provider/resource Regions, literal AZs, up to 16 counted instances with bounded local/variable lists or `element(..., count.index)` | Account identity, data sources, arbitrary expressions and `for_each` expansion stay unknown. No failover or RTO/RPO guarantee. |
| Routing | Inline/standalone default IPv4/IPv6 routes, subnet/table references, explicit main associations, IGW/NAT/egress-only targets, DB subnet-group/SG references | Implicit external tables, unresolved/indexed references and full packet paths are not inferred. Routes do not prove reachability. |
| Retention | Lifecycle status/filter scope/current/noncurrent days, versioning and declared replication links, TTL with unknown writer, logs and Standard history configuration | Dynamic blocks, complex filters, data presence and physical deletion timing remain uncertain. Names do not establish replicas. |
| Backup selection | Explicit includes/excludes/plan links, bounded local exact tags, native RDS retention, source/copy retention with explicit override versus inheritance | Tag OR and StringEquals AND predicates require no mixed ARN selection. Wildcard/negated/mixed selectors are unsupported. Missing tags stay unknown because provider defaults may supply them. Opt-in, backup/restore execution and effective accounts are unverified. |
| Entry paths | REST auth/API/backend references, URL auth, both public permission actions/constraints, SQS/function timeout relationships | References are not executable paid paths. Restricted/qualified, v2/composite or unresolved paths remain conservative. Runtime invocation stays unknown. |

New deterministic checks flag fully observed counted instances in one AZ,
invalid SQS timeout mappings and enabled versioned lifecycles with all-object
current expiration but absent noncurrent expiration. Explicit risk assessments
and engineering explanations add no price/effort recipes. Unknown/dynamic/
conditional controls prevent unsupported findings. Routing and selection facts
support contextual review without calling every intentional public subnet or
excluded development database a defect.

### Nested configuration details (2026-10-28)

A hard test review (a 74-resource payments platform) showed the model never
saw several high-risk configurations, so `resource_details.py` adds a
`details` object for these types, in fixed vocabulary only:

| Type | What the model now sees |
|---|---|
| `aws_security_group` | Each ingress rule's ports, protocol and source class (internet, address range, another group). Dynamic `ingress` blocks are included when their `for_each` resolves, and marked conditional when it doesn't. |
| `aws_iam_role` | Who is trusted (service, whole account, GitHub OIDC, SAML), which guarding condition keys are present, and for GitHub what the `sub` condition admits (organization wildcard, any ref, one branch, one environment). |
| IAM policies | Per statement: allowlisted sensitive actions by name (`iam:PassRole`, `lambda:CreateFunction`, ...), other actions counted, NotAction, resource scope. |
| Policy attachments | The AWS managed policy's name when it's on an allowlist, otherwise a generic label. |
| `aws_cloudfront_distribution` | Each origin's target kind and origin protocol policy or S3 access control, viewer protocol policies, WAF attachment, certificate and minimum TLS. |
| `aws_ecs_task_definition`, `aws_lambda_function` | Image tag kind; environment variable counts, including secret-looking names with literal values. Names and values are never copied. |
| `aws_sqs_queue` | The dead-letter queue it redrives to and its receive count. |
| DB parameter groups | Allowlisted security and logging parameters (`rds.force_ssl`, `require_secure_transport`, ...). |

New allowlisted scalar settings cover listeners (port, protocol, SSL policy,
action), Aurora instances, ElastiCache node type and auth token presence, SQS
visibility timeout and KMS key presence, ECR, ECS services, Secrets Manager
recovery window, WAF scope and alarm namespaces. A setting written as
`has X` reports only whether X is set. Conditionals may now choose between
short list literals (`var.enabled ? [1] : []`), which also lets the security
group rule see enabled dynamic ingress blocks.

Placement-only observation bundles (the default region and an unknown
account, nothing else) are no longer emitted per resource: on that test they
filled the byte budget before security groups or queues were reached. The
summary states them once as `default_placement`, and
`analysis_coverage.placement_only_resources` counts them.

### What the code says about itself (2026-10-29)

A second hard test (a telehealth platform submitted with a brief calling it
a "throwaway sandbox with synthetic data") showed the model taking the brief's
word, though the code tags everything `Environment = prod` and
`DataClass = phi`. The summary now carries `declared_context`: environment
and data-classification labels from provider `default_tags`, resource `tags`
and environment-named root variables. Keys and values both come from fixed
lists (`prod`, `staging`, `dev`, `sandbox`, ... and `phi`, `pii`, `pci`,
`confidential`, ...); any other value is dropped, so no free text reaches the
model through a tag. The prompt treats the brief's unverifiable claims as
unverified and asks the model to name contradictions with `declared_context`.

A Lambda `reserved_concurrent_executions` of 0 is shown as "never runs
(every invocation is throttled)", after the model read it as "unreserved".

## Bounds and publication

The existing 80-resource cap remains. Past it, resources are kept by risk, not
alphabet: access decisions (policies, ACLs, permissions, ingress rules, secrets,
SSM parameters, authorizers, routes) first, then data stores and anything with
listed settings, then other services, then wiring (route table associations,
subnet groups, EIPs, zones). Within a tier every type's first resource comes
before any type's second. Alphabetical order had cut every S3, security group,
SQS and SSM resource from a 119-resource test. Observations additionally enforce 48,000
serialized UTF-8 bytes and 256 facts, 16 expanded instances, 32 rule/reference
items and 16 copy actions per rule. Omissions are counted; dynamic blocks are
incomplete. Tokenizer counts remain explicitly unmeasured; byte bounds are not
presented as an exact model token budget. Missing output never proves absence.
Each observation resolution also has an 8,192-byte work budget and a 4,096-character
expression bound; exhaustion stays unknown. A configured noncurrent-expiration
block is distinct from an absent block, even when its day field is uninspected
or incomplete.

Reports and HTML/JSON exports include sanitized scope limits. Chat uses the
same observations, removes detail under its context bound with explicit omission
notices, and disallows citations to trimmed resources. Diagrams show known
Region/AZ details from those facts. Prompts preserve the same boundaries.

## Frozen expectation reconciliation

The separate coverage suite now records **18 passing / 8 failing checks**,
two scanner modes per expectation: nine of thirteen raw expectations pass.
Remaining: F04-D-07 has route facts but its probe requires a finding;
F07-D-03/D-04/D-05 demand public invocation, a paid backend path and a public
diagram edge without the fixture's missing permission/integration chain.
E01/E03 in the semantic oracle qualify those expectations. Failures stay visible.

Two other lexical probes reject correct richer output: F06-D-04 flags any
Region/account text; F08-D-04 flags affirmative versioning evidence.
[Probe errata](../tests/backend/adversarial/PROBE_ERRATA_2026-10-23.md) retain raw
failures and add typed supplemental contracts with negative controls. Frozen
key, fixtures, saved results and historical model inputs remain unchanged.

## Reviewed primary sources

- [Provider configuration](https://developer.hashicorp.com/terraform/language/block/provider)
  and [module mappings](https://developer.hashicorp.com/terraform/language/meta-arguments/providers).
- [Resource Region overrides](https://registry.terraform.io/providers/hashicorp/aws/6.20.0/docs/resources/instance.html).
- [VPC route tables](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html).
- [S3 expiration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html).
- [Backup selection](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_BackupSelection.html)
  and [conditions](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_Conditions.html).
- Lambda URL/SQS and copy-retention sources are pinned in the
  [semantic errata](../tests/backend/adversarial/SEMANTIC_ERRATA_2026-10-23.md).

Sources were checked during implementation on 2026-10-23/24. No paid model run,
Terraform execution or live deployment established this local coverage.
