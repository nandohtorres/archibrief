# Semantic errata for the frozen adversarial cases

Oracle sidecar version: `semantic-errata@2026-10-23`. This supplements the
frozen key and historical results; it does not change their hashes, scores or
fixtures. Supplementary executable assertions and expanded extraction coverage
remain pending. These corrections must be included when designing the next
model rubric; old fixture comments are not themselves an AWS authority.

The dangerous variants were inspected in families 06, 07 and 08. AWS sources
below were checked on 2026-10-23. Static code establishes configuration, not
successful deployment or observed runtime behavior.

| ID | Fixture observation | Correct grading boundary |
|---|---|---|
| E01 | F07: function URL sets `authorization_type = "NONE"`; no public invocation resource policy is declared | Identify the authentication setting, but do not assert proven public invocation. Lambda requires public resource permissions too; new URLs require both invocation actions. |
| E02 | F07: function timeout 300 s, queue visibility 30 s | Identify a mapping configuration AWS rejects, not an observed redelivery/spend scenario. Use a separate deployable fixture for retry tuning. |
| E03 | F07: unauthenticated API method, without a declared method-to-function integration | Do not infer a callable paid inference path from a nearby Lambda or method name. Linkage and invocation remain unproven. |
| E04 | F06: backup selection names dev; prod RDS independently declares seven-day native retention | Prod is not selected by this AWS Backup selection. Do not call prod entirely unbacked or assume the declared retention meets the workload's recovery needs. |
| E05 | F08: bucket named `uploads_replica`, without S3 replication configuration | Treat both buckets' lifecycle configuration independently. A name does not establish replication. |
| E06 | F06: last source backup rule retains one day; its copy action has no lifecycle override | Distinguish explicit source retention from the copy's derived retention. AWS documents inheritance and overrides; do not invent an explicit destination setting. |

Primary sources:

- [Lambda URL authentication and resource permissions](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html) (E01).
- [Lambda SQS event-source mapping validation](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html) (E02).
- [RDS native automated backup retention](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.BackupRetention.html) (E04).
- [AWS Backup copy retention and overrides](https://docs.aws.amazon.com/aws-backup/latest/devguide/recov-point-create-a-copy.html) (E06).

E03/E05 are observations about missing declared relationships in these slices,
not claims that the relationships are absent in deployed environments. The next
rubric should preserve raw frozen verdicts and report revised adjudication
separately. No paid model run or Terraform execution established these errata.
