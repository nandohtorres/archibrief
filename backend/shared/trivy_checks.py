"""The Trivy checks ArchiBrief trusts, and how each becomes a finding (ADR-0048).

Trivy reports dozens of checks; many are noise for a review like this
(e.g. "use a customer-managed KMS key" fires on nearly every bucket and
was trap f03's false positive). Only the checks listed here are kept.
Every entry was observed firing on real Terraform in this repo's samples
or trap fixtures before being added, and every Well-Architected ID was
checked against the retrieval corpus.

Finding text is written here, not taken from Trivy's output, so nothing a
submitter wrote reaches finding text except a sanitized resource name.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrustedCheck:
    concern: str  # what the check is about; Python rules for the same concern step aside
    category: str  # backend.shared.models.finding.FindingCategory value
    title: str  # "{name}" is the sanitized, module-scoped resource name
    detail: str  # what the setting is, used in evidence
    risk: str
    recommendation: str
    framework: tuple[str, ...]


_S3_PUBLIC = (
    "s3_public_access",
    "exposure",
    "Public access to S3 bucket '{name}' is not fully blocked",
)
_S3_PUBLIC_RISK = (
    "A later ACL or bucket-policy change could expose the bucket's contents to the internet."
)
_S3_PUBLIC_FIX = (
    "Attach aws_s3_bucket_public_access_block with block_public_acls, block_public_policy, "
    "ignore_public_acls and restrict_public_buckets all set to true."
)
_SECURITY = "AWS Well-Architected: Security Pillar"
_RELIABILITY = "AWS Well-Architected: Reliability Pillar"
_OPS = "AWS Well-Architected: Operational Excellence Pillar"

TRUSTED_CHECKS: dict[str, TrustedCheck] = {
    "AWS-0086": TrustedCheck(
        *_S3_PUBLIC,
        "block_public_acls is not enabled",
        _S3_PUBLIC_RISK,
        _S3_PUBLIC_FIX,
        (_SECURITY, "SEC08-BP04"),
    ),
    "AWS-0087": TrustedCheck(
        *_S3_PUBLIC,
        "block_public_policy is not enabled",
        _S3_PUBLIC_RISK,
        _S3_PUBLIC_FIX,
        (_SECURITY, "SEC08-BP04"),
    ),
    "AWS-0091": TrustedCheck(
        *_S3_PUBLIC,
        "ignore_public_acls is not enabled",
        _S3_PUBLIC_RISK,
        _S3_PUBLIC_FIX,
        (_SECURITY, "SEC08-BP04"),
    ),
    "AWS-0093": TrustedCheck(
        *_S3_PUBLIC,
        "restrict_public_buckets is not enabled",
        _S3_PUBLIC_RISK,
        _S3_PUBLIC_FIX,
        (_SECURITY, "SEC08-BP04"),
    ),
    "AWS-0090": TrustedCheck(
        "s3_versioning",
        "recovery",
        "S3 bucket '{name}' does not have versioning enabled",
        "versioning is not enabled",
        "Accidental or malicious object deletion or overwrite cannot be recovered.",
        'Enable aws_s3_bucket_versioning with status = "Enabled".',
        (_RELIABILITY, "REL09-BP01"),
    ),
    "AWS-0107": TrustedCheck(
        "sg_admin_ingress",
        "exposure",
        "Security group '{name}' allows SSH or RDP from anywhere",
        "ingress from 0.0.0.0/0 or ::/0 reaches SSH (22) or RDP (3389)",
        "Remote administration ports are reachable from the entire internet.",
        "Restrict ingress to specific CIDR ranges, a bastion, or use SSM Session Manager.",
        (_SECURITY, "SEC05-BP02", "CIS Controls v8: 4.4"),
    ),
    "AWS-0026": TrustedCheck(
        "ebs_encryption",
        "encryption",
        "EBS volume '{name}' is not encrypted",
        "encrypted is not true",
        "Data at rest on the volume is unencrypted.",
        "Set encrypted = true (and kms_key_id if a customer-managed key is required).",
        (_SECURITY, "SEC08-BP02"),
    ),
    "AWS-0080": TrustedCheck(
        "rds_encryption",
        "encryption",
        "RDS instance '{name}' does not encrypt its storage",
        "storage_encrypted is not true (variable defaults included)",
        "Database storage is unencrypted at rest.",
        "Set storage_encrypted = true; it cannot be changed after the instance is created.",
        (_SECURITY, "SEC08-BP02"),
    ),
    "AWS-0180": TrustedCheck(
        "rds_public",
        "exposure",
        "RDS instance '{name}' is publicly accessible",
        "publicly_accessible = true",
        "The database gets a public endpoint and is one security-group mistake from the internet.",
        "Set publicly_accessible = false and reach the database from inside the VPC.",
        (_SECURITY, "SEC05-BP01"),
    ),
    "AWS-0024": TrustedCheck(
        "dynamodb_pitr",
        "recovery",
        "DynamoDB table '{name}' does not have point-in-time recovery enabled",
        "point_in_time_recovery is not enabled",
        "Accidental writes or deletes cannot be rolled back to a prior point in time.",
        "Set point_in_time_recovery { enabled = true }.",
        (_RELIABILITY, "REL09-BP01"),
    ),
    "AWS-0164": TrustedCheck(
        "subnet_public_ip",
        "exposure",
        "Subnet '{name}' gives instances a public IP by default",
        "map_public_ip_on_launch = true",
        "Instances launched into this subnet are reachable from the internet by default.",
        "Set map_public_ip_on_launch = false unless the subnet is meant to be public.",
        (_SECURITY, "SEC05-BP01"),
    ),
    "AWS-0095": TrustedCheck(
        "sns_encryption",
        "encryption",
        "SNS topic '{name}' is not encrypted",
        "kms_master_key_id is not set",
        "Messages are stored unencrypted at rest.",
        "Set kms_master_key_id on the topic.",
        (_SECURITY, "SEC08-BP02"),
    ),
    "AWS-0077": TrustedCheck(
        "rds_backup_retention",
        "recovery",
        "RDS instance '{name}' keeps backups for one day or less",
        "backup_retention_period is unset or 1",
        "A problem noticed after a day can't be restored from backup.",
        "Set backup_retention_period to match your recovery needs (for example 7 or more days).",
        (_RELIABILITY, "REL09-BP01"),
    ),
    "AWS-0177": TrustedCheck(
        "rds_deletion_protection",
        "recovery",
        "RDS instance '{name}' has no deletion protection",
        "deletion_protection is not true",
        "The database can be deleted by a single mistaken apply or API call.",
        "Set deletion_protection = true for databases that hold data you need.",
        (_RELIABILITY, "REL09-BP01"),
    ),
    "AWS-0001": TrustedCheck(
        "apigw_access_logging",
        "observability",
        "API Gateway stage '{name}' has no access logging",
        "access_log_settings is not configured",
        "Requests to the API can't be traced during an incident.",
        "Configure access_log_settings with a CloudWatch Logs destination.",
        (_OPS, "SEC04-BP01"),
    ),
    "AWS-0010": TrustedCheck(
        "cloudfront_logging",
        "observability",
        "CloudFront distribution '{name}' has no access logging",
        "logging_config is not set",
        "Requests to the distribution can't be traced during an incident.",
        "Add a logging_config block pointing at a log bucket.",
        (_OPS, "SEC04-BP01"),
    ),
    "AWS-0011": TrustedCheck(
        "cloudfront_waf",
        "exposure",
        "CloudFront distribution '{name}' has no WAF in front of it",
        "web_acl_id is not set",
        "Common web attacks and abusive traffic reach the origin unfiltered.",
        "Associate an AWS WAF web ACL with the distribution.",
        (_SECURITY, "SEC05-BP03"),
    ),
}

TRUSTED_CHECK_IDS = frozenset(TRUSTED_CHECKS)

# Concerns Trivy covers well enough that ArchiBrief's own Python rule for
# the same concern steps aside when Trivy ran successfully.
TRIVY_OWNED_CONCERNS = frozenset(check.concern for check in TRUSTED_CHECKS.values())
