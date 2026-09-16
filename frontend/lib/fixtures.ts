import type { PreflightField, ProgressStage, ReviewReport } from "./contracts";

const retrievedAt = "2026-09-08T19:02:00Z";
const createdAt = "2026-09-08T19:05:00Z";

export const fixturePreflightFields: PreflightField[] = [
  {
    id: "expected_traffic_scale",
    label: "Traffic and scale",
    question: "What peak request rate should this workload support?",
    policy: "answer",
    value: "40 requests/second",
    reason: "Capacity and concurrency recommendations depend on a workload-specific target.",
  },
  {
    id: "availability_criticality",
    label: "Availability target",
    question: "What availability target should the review evaluate?",
    policy: "default",
    value: "",
    shownDefault: "99.9% monthly availability; a brief interruption is tolerable",
    reason:
      "A named conservative scenario can be modeled, and dependent findings will be typed as assumptions.",
  },
  {
    id: "regulatory_data_residency",
    label: "Regulatory and data residency",
    question: "Which regulatory or residency requirements apply?",
    policy: "stopped",
    value: "",
    reason:
      "ArchiBrief cannot infer legal obligations safely. Related conclusions stop and remain not observable until evidence is supplied.",
  },
];

export const fixtureProgressStages: ProgressStage[] = [
  {
    id: "ingest",
    label: "Ingest",
    description: "Validate and statically parse submitted Terraform",
  },
  {
    id: "preflight",
    label: "Preflight",
    description: "Apply the recorded baseline answers field by field",
  },
  {
    id: "rules",
    label: "Rule checks",
    description: "Run deterministic security and reliability checks",
  },
  {
    id: "retrieve",
    label: "Retrieve evidence",
    description: "Find versioned AWS guidance and exact passages",
  },
  { id: "reason", label: "Reason", description: "Synthesize bounded, typed findings" },
  { id: "validate", label: "Validate", description: "Reject malformed or unsupported output" },
  { id: "finalize", label: "Finalize", description: "Write the immutable evidence ledger" },
];

export const fixtureReport: ReviewReport = {
  review_id: "review-fixture-20260908",
  owner_id: "fixture-user",
  status: "complete",
  terraform_repo_ref: "github.com/example/payments-api@a91f3c2",
  created_at: createdAt,
  cost_estimate_tier: "medium",
  baseline_answers: [
    {
      field: "expected_traffic_scale",
      label: "Traffic and scale",
      outcome: "answered",
      value: "40 requests/second peak",
      policy_version: "preflight-1.2",
    },
    {
      field: "availability_criticality",
      label: "Availability target",
      outcome: "assumption",
      value: "99.9% monthly availability; brief interruption tolerable",
      policy_version: "preflight-1.2",
    },
    {
      field: "regulatory_data_residency",
      label: "Regulatory and data residency",
      outcome: "not-observable",
      value: "Not supplied; dependent conclusions stopped",
      policy_version: "preflight-1.2",
    },
  ],
  findings: [
    {
      presentation: { priority: "high", short_label: "High risk" },
      record: {
        finding_id: "finding-001",
        review_id: "review-fixture-20260908",
        category: "exposure",
        type: "deterministic-rule-result",
        finding: "Bucket-level S3 public-access protection is not declared",
        evidence:
          "The submitted repository contains payments-audit-logs but no aws_s3_bucket_public_access_block resource for it. An account-level control could still exist outside the submitted code.",
        citation: {
          source_url:
            "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html",
          source_edition: "Amazon S3 User Guide · retrieved snapshot",
          retrieved_at: retrievedAt,
          canonical_url:
            "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html",
          document_id: "aws-s3-user-guide",
          chunk_id: "sec-s3-bpa-07",
          content_hash: "sha256:fixture-9eb13d6",
          heading_path: "Managing public access > Block Public Access",
          exact_text_span:
            "Illustrative fixture span. Production output contains the exact captured AWS passage.",
          parser_version: "normalizer-0.1",
          corpus_version: "2026-09-06",
        },
        confidence: 0.98,
        confidence_inputs: { evidence_directness: 1, source_agreement: 0.96, rule_determinism: 1 },
        risk_impact:
          "A bucket-level guardrail is absent from the submitted code. Effective exposure must still be checked against account-level settings and bucket policy.",
        recommendation:
          "Enable S3 Block Public Access at both bucket and account levels, then validate the effective bucket policy.",
        framework_mapping: ["AWS Well-Architected · Security", "AWS FSBP · S3.1"],
        alternatives_considered: [
          {
            option: "Rely on a restrictive bucket policy",
            reason_rejected:
              "A later policy change can reopen access without the independent block-public-access guardrail.",
          },
          {
            option: "Monitor for public exposure only",
            reason_rejected: "Detection occurs after the preventive control has already failed.",
          },
        ],
        depth_level: "lightweight",
        model_id: null,
        prompt_version: null,
        corpus_version: "2026-09-06",
        retrieved_chunk_ids: ["sec-s3-bpa-07"],
        deterministic_rule_version: "rules-2026.09.1",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
    {
      presentation: { priority: "high", short_label: "High risk" },
      record: {
        finding_id: "finding-002",
        review_id: "review-fixture-20260908",
        category: "iam",
        type: "deterministic-rule-result",
        finding: "Lambda execution role grants s3:* on *",
        evidence: "The submitted inline policy contains Action: s3:* and Resource: *.",
        citation: {
          source_url: "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
          source_edition: "IAM User Guide · retrieved snapshot",
          retrieved_at: retrievedAt,
          canonical_url: "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
          document_id: "aws-iam-best-practices",
          chunk_id: "iam-bp-002",
          content_hash: "sha256:fixture-154de63",
          heading_path: "Apply least-privilege permissions",
          exact_text_span:
            "Illustrative fixture span. Production output contains the exact captured AWS passage.",
          parser_version: "normalizer-0.1",
          corpus_version: "2026-09-06",
        },
        confidence: 0.95,
        confidence_inputs: { evidence_directness: 1, source_agreement: 0.91, rule_determinism: 1 },
        risk_impact:
          "Compromise of the function could expose unrelated S3 resources beyond the audit bucket it needs.",
        recommendation:
          "Limit the policy to required S3 actions and specific bucket ARNs, then refine it using observed access.",
        framework_mapping: ["AWS Well-Architected · Security", "SEC03-BP02"],
        alternatives_considered: [
          {
            option: "Attach AWS managed ReadOnlyAccess",
            reason_rejected:
              "It remains broader than the workload's actual S3 operations and resources.",
          },
        ],
        depth_level: "lightweight",
        model_id: null,
        prompt_version: null,
        corpus_version: "2026-09-06",
        retrieved_chunk_ids: ["iam-bp-002"],
        deterministic_rule_version: "rules-2026.09.1",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
    {
      presentation: { priority: "high", short_label: "High risk" },
      record: {
        finding_id: "finding-003",
        review_id: "review-fixture-20260908",
        category: "observability",
        type: "deterministic-rule-result",
        finding: "No account-wide CloudTrail trail is observable",
        evidence:
          "No aws_cloudtrail resource appears in the submitted repository. An organization-managed trail may exist outside this review boundary.",
        citation: {
          source_url:
            "https://docs.aws.amazon.com/securityhub/latest/userguide/cloudtrail-controls.html",
          source_edition: "AWS Security Hub controls · retrieved snapshot",
          retrieved_at: retrievedAt,
          canonical_url:
            "https://docs.aws.amazon.com/securityhub/latest/userguide/cloudtrail-controls.html",
          document_id: "aws-fsbp-cloudtrail",
          chunk_id: "fsbp-cloudtrail-1",
          content_hash: "sha256:fixture-44607ad",
          heading_path: "CloudTrail controls",
          exact_text_span:
            "Illustrative fixture span. Production output contains the exact captured AWS passage.",
          parser_version: "normalizer-0.1",
          corpus_version: "2026-09-06",
        },
        confidence: 0.9,
        confidence_inputs: {
          evidence_directness: 0.88,
          source_agreement: 0.92,
          rule_determinism: 0.9,
        },
        risk_impact:
          "Account activity may lack a durable audit trail if no externally managed trail exists.",
        recommendation:
          "Confirm organization-level coverage; otherwise create a multi-Region trail with log-file validation.",
        framework_mapping: [
          "AWS Well-Architected · Operational Excellence",
          "AWS FSBP · CloudTrail.1",
        ],
        alternatives_considered: [],
        depth_level: "lightweight",
        model_id: null,
        prompt_version: null,
        corpus_version: "2026-09-06",
        retrieved_chunk_ids: ["fsbp-cloudtrail-1"],
        deterministic_rule_version: "rules-2026.09.1",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
    {
      presentation: { priority: "review", short_label: "Review" },
      record: {
        finding_id: "finding-004",
        review_id: "review-fixture-20260908",
        category: "recovery",
        type: "assumption",
        finding: "Multi-AZ is not enabled for payments-db",
        evidence:
          "The submitted resource sets multi_az = false; the availability target is a named preflight assumption.",
        citation: {
          source_url:
            "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html",
          source_edition: "Amazon RDS User Guide · retrieved snapshot",
          retrieved_at: retrievedAt,
          canonical_url:
            "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html",
          document_id: "aws-rds-multiaz",
          chunk_id: "rds-multiaz-05",
          content_hash: "sha256:fixture-9ab32f8",
          heading_path: "Multi-AZ deployments",
          exact_text_span:
            "Illustrative fixture span. Production output contains the exact captured AWS passage.",
          parser_version: "normalizer-0.1",
          corpus_version: "2026-09-06",
        },
        confidence: 0.68,
        confidence_inputs: {
          evidence_directness: 1,
          source_agreement: 0.9,
          rule_determinism: 0.52,
        },
        risk_impact:
          "A database outage may require manual recovery and conflict with the assumed availability target.",
        recommendation:
          "Enable Multi-AZ if the 99.9% availability target is confirmed as a hard requirement.",
        framework_mapping: ["AWS Well-Architected · Reliability", "REL10-BP01"],
        alternatives_considered: [
          {
            option: "Use a read replica",
            reason_rejected:
              "A read replica does not provide the same managed synchronous standby and automatic failover behavior.",
          },
        ],
        depth_level: "lightweight",
        model_id: "anthropic.claude-fixture",
        prompt_version: "reason-lightweight-1.4",
        corpus_version: "2026-09-06",
        retrieved_chunk_ids: ["rds-multiaz-05"],
        deterministic_rule_version: "rules-2026.09.1",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
    {
      presentation: { priority: "confirmed", short_label: "Confirmed" },
      record: {
        finding_id: "finding-005",
        review_id: "review-fixture-20260908",
        category: "encryption",
        type: "fact",
        finding: "RDS storage encryption is declared",
        evidence:
          "The submitted Terraform declares storage_encrypted = true and a KMS key identifier.",
        citation: {
          source_url:
            "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html",
          source_edition: "Amazon RDS User Guide · retrieved snapshot",
          retrieved_at: retrievedAt,
          canonical_url:
            "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html",
          document_id: "aws-rds-encryption",
          chunk_id: "rds-encryption-03",
          content_hash: "sha256:fixture-df7b381",
          heading_path: "Encrypting Amazon RDS resources",
          exact_text_span:
            "Illustrative fixture span. Production output contains the exact captured AWS passage.",
          parser_version: "normalizer-0.1",
          corpus_version: "2026-09-06",
        },
        confidence: 0.99,
        confidence_inputs: { evidence_directness: 1, source_agreement: 0.98, rule_determinism: 1 },
        risk_impact:
          "The declaration supports encryption at rest, but this static review does not prove deployed state or key-policy correctness.",
        recommendation:
          "No baseline change indicated; confirm key ownership and rotation requirements separately.",
        framework_mapping: ["AWS Well-Architected · Security", "SEC08-BP02"],
        alternatives_considered: [],
        depth_level: "lightweight",
        model_id: null,
        prompt_version: null,
        corpus_version: "2026-09-06",
        retrieved_chunk_ids: ["rds-encryption-03"],
        deterministic_rule_version: "rules-2026.09.1",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
    {
      presentation: { priority: "unknown", short_label: "Not observable" },
      record: {
        finding_id: "finding-006",
        review_id: "review-fixture-20260908",
        category: "availability",
        type: "not-observable",
        finding: "Data-residency requirements were not supplied",
        evidence:
          "The workload brief does not identify regulatory or geographic processing constraints.",
        citation: null,
        confidence: 1,
        confidence_inputs: { evidence_directness: 1, source_agreement: 1, rule_determinism: 1 },
        risk_impact:
          "ArchiBrief cannot make compliance-like or residency conclusions without user-provided requirements.",
        recommendation:
          "Confirm applicable requirements and include them in a new review's workload brief.",
        framework_mapping: [],
        alternatives_considered: [],
        depth_level: "lightweight",
        model_id: null,
        prompt_version: null,
        corpus_version: null,
        retrieved_chunk_ids: [],
        deterministic_rule_version: "preflight-1.2",
        parent_finding_id: null,
        created_at: createdAt,
      },
    },
  ],
};
