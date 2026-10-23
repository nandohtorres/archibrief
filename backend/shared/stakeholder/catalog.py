"""Plain-language text, fix recipes and the cost of not fixing, per rule.

Every rule finding has a concern (backend/lambdas/rule_engine/handler.py,
backend/shared/trivy_checks.py). Each concern's entry here is written
once, by hand, for a reader who isn't an engineer: what the problem is in
plain terms, an everyday comparison, what could happen, what the fix
adds (priced by pricing.py) and roughly how long it takes.

"Cost of not fixing" never makes up a number. It either cites a
published figure (source and year named) or explains how to estimate it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]
SEVERITIES: tuple[Severity, ...] = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class Harm:
    headline: str
    detail: str
    source_name: str | None = None
    source_url: str | None = None
    # How to estimate it when there's no published figure to cite.
    method: str | None = None


_IBM = "IBM Cost of a Data Breach Report 2026"
_IBM_URL = "https://www.ibm.com/reports/data-breach"

HARMS: dict[str, Harm] = {
    "data_breach": Harm(
        "Average data breach: $4.99 million",
        "The global average cost of a breach, counting investigation, notification, "
        "lost business and fines. Breaches in the US averaged $11.5 million.",
        _IBM,
        _IBM_URL,
    ),
    "slow_detection": Harm(
        "Breaches take 247 days on average to find and contain",
        "Without an audit trail or logs, a break-in is found later, and breaches that "
        "last more than 200 days averaged $5.65 million against $4.32 million for "
        "faster ones.",
        _IBM,
        _IBM_URL,
    ),
    "data_loss": Harm(
        "Average ransomware recovery: $1.7 million",
        "What organizations spent to recover from a ransomware attack, not counting "
        "any ransom paid. Backups and version history are what make recovery possible.",
        "Sophos State of Ransomware 2026",
        "https://www.sophos.com/en-us/content/state-of-ransomware",
    ),
    "downtime": Harm(
        "Every hour offline costs what the service earns or saves in an hour",
        "There's no fair average for downtime: it depends on the business.",
        method="Multiply your revenue (or staff time saved) per hour by the hours a "
        "failure would keep the service down.",
    ),
    "runaway_bill": Harm(
        "A bug or abuse can keep running up the bill until someone notices",
        "There's no fair average: the cost is how long it runs times the price per request.",
        method="Estimate your busiest hour of traffic, multiply it by how many hours "
        "it could run unnoticed, and price that at the service's per-request rate.",
    ),
}


@dataclass(frozen=True)
class Component:
    item: str  # a pricing.PRICE_ITEMS key
    quantity: int = 1
    # Read the size from this setting on the finding's resource
    # (terraform_resources), e.g. instance_class for a standby database.
    size_setting: str | None = None


@dataclass(frozen=True)
class Recipe:
    severity: Severity
    title: str
    analogy: str
    what_could_happen: str
    action: str
    components: tuple[Component, ...]
    effort_hours: tuple[float, float]
    harm: str
    # Shown under the cost when the fix has a catch worth knowing about.
    # "{item}" is replaced with that price-table item's monthly price.
    caveat: str | None = None


_FREE = (Component("none"),)

RECIPES: dict[str, Recipe] = {
    "s3_public_access": Recipe(
        "high",
        "A storage bucket isn't locked against public sharing",
        "Like a filing cabinet whose lock can be switched off by one wrong setting.",
        "One mistaken permission change could put every file in it on the open internet.",
        "Turn on all four of AWS's public-access blocks for the bucket.",
        _FREE,
        (0.25, 1),
        "data_breach",
    ),
    "s3_encryption": Recipe(
        "medium",
        "The code doesn't say how stored files are encrypted",
        "Like a safe that came with a factory lock nobody chose or wrote down.",
        "S3 encrypts new files with an AWS-owned key by default, but nothing here "
        "chooses or records that, and nobody can limit who decrypts sensitive files.",
        "Declare the bucket's encryption in the code, with your own key for sensitive data.",
        _FREE,
        (0.5, 1),
        "data_breach",
        caveat="Declaring S3's default encryption is free; a customer-managed key adds "
        "{kms_key} and lets you control who can decrypt.",
    ),
    "s3_versioning": Recipe(
        "medium",
        "Deleted or overwritten files can't be brought back",
        "Like a document with no undo and no saved drafts.",
        "A mistake, a bad script or ransomware could wipe files for good.",
        "Turn on versioning so old copies are kept, with a rule that expires them.",
        (Component("s3_old_versions"),),
        (0.25, 1),
        "data_loss",
    ),
    "s3_public_policy": Recipe(
        "critical",
        "A storage bucket lets anyone on the internet in",
        'Like leaving a filing cabinet on the sidewalk with a sign saying "help yourself".',
        "Anyone who finds the bucket's address can read or change what's in it.",
        "Remove the public permission and grant access only to the apps that need it.",
        _FREE,
        (1, 4),
        "data_breach",
    ),
    "sg_open_ingress": Recipe(
        "critical",
        "Sensitive ports are open to the whole internet",
        "Like leaving the back door of the server room unlocked, facing the street.",
        "Automated scanners find open database and admin ports within hours and try to break in.",
        "Allow those ports only from your own network or other services in the VPC.",
        _FREE,
        (1, 4),
        "data_breach",
    ),
    "sg_admin_ingress": Recipe(
        "critical",
        "Remote admin login is open to the whole internet",
        "Like a front-door keypad anyone in the world can keep guessing at.",
        "Attackers constantly try passwords and known flaws on SSH and RDP.",
        "Close the port and log in through AWS Systems Manager Session Manager instead, "
        "which has no extra charge.",
        _FREE,
        (1, 4),
        "data_breach",
    ),
    "subnet_public_ip": Recipe(
        "medium",
        "New servers get a public internet address by default",
        "Like every new office getting a door straight onto the street.",
        "A server launched here for internal use is reachable from the internet "
        "without anyone choosing that.",
        "Turn the default off and give public addresses only to servers that need them.",
        _FREE,
        (1, 4),
        "data_breach",
        caveat="If private servers still need to reach the internet, a NAT gateway adds "
        "{nat_gateway}.",
    ),
    "ebs_encryption": Recipe(
        "high",
        "A server's disk isn't encrypted",
        "Like a laptop with no disk password.",
        "A copied disk or snapshot can be read by whoever has it.",
        "Copy the disk to an encrypted one and switch over, or turn on encryption by "
        "default for the account.",
        _FREE,
        (2, 8),
        "data_breach",
        caveat="Existing disks can't be encrypted in place, so switching needs a short "
        "maintenance window.",
    ),
    "rds_encryption": Recipe(
        "high",
        "The database's storage isn't encrypted",
        "Like keeping customer records in an unlocked drawer.",
        "A copied backup or snapshot can be read by whoever has it.",
        "Restore an encrypted copy of the database and switch the app over.",
        _FREE,
        (4, 16),
        "data_breach",
        caveat="Encryption can't be turned on for a running database, so this needs a "
        "planned switch-over and some downtime.",
    ),
    "rds_public": Recipe(
        "critical",
        "The database has a public internet address",
        "Like putting the safe in the shop window.",
        "One firewall mistake away from attackers trying to log in to the database directly.",
        "Make the database private and reach it only from inside the network.",
        _FREE,
        (1, 4),
        "data_breach",
    ),
    "rds_multi_az": Recipe(
        "medium",
        "The database has no standby copy",
        "Like a shop with one key and no spare.",
        "If its data center has a problem, the database, and the app with it, is down "
        "until AWS recovers it.",
        "Turn on Multi-AZ so AWS keeps a standby copy in a second data center and "
        "switches to it automatically.",
        (Component("rds_standby", size_setting="instance_class"),),
        (0.5, 2),
        "downtime",
        caveat="Multi-AZ roughly doubles the database's instance and storage cost.",
    ),
    "dynamodb_pitr": Recipe(
        "medium",
        "The table can't be rewound to before a mistake",
        "Like a spreadsheet with no version history.",
        "A bad deploy or script that corrupts data can't be undone.",
        "Turn on point-in-time recovery, which keeps 35 days of history.",
        (Component("pitr_storage"),),
        (0.25, 0.5),
        "data_loss",
    ),
    "iam_wildcard": Recipe(
        "critical",
        "A permission grants access to everything",
        "Like handing a contractor a master key to every room instead of one.",
        "If anything using this permission is hacked, the attacker gets the same unlimited access.",
        "Limit the permission to the specific actions and resources it really needs.",
        _FREE,
        (2, 8),
        "data_breach",
    ),
    "iam_trust": Recipe(
        "high",
        "An outside account can take on this role with no extra check",
        "Like a building badge that works for anyone who knows the badge number.",
        "Another AWS account could use this role's permissions without proving who it is.",
        "Add an external ID or identity condition to the role's trust policy.",
        _FREE,
        (1, 4),
        "data_breach",
    ),
    "iam_compute_broad_managed": Recipe(
        "high",
        "Running code has far more access than it needs",
        "Like a delivery driver with keys to the whole warehouse.",
        "If the server or function is hacked, the attacker can reach everything this "
        "access allows, such as every storage bucket.",
        "Replace the broad AWS policy with one that names only the resources the code uses.",
        _FREE,
        (2, 6),
        "data_breach",
    ),
    "ec2_imdsv2": Recipe(
        "high",
        "The server hands out its access keys too easily",
        "Like a hotel front desk that gives a room key to anyone who calls.",
        "A common web flaw (SSRF) can trick the server into revealing its AWS keys. "
        "This is how the 2019 Capital One breach happened.",
        "Require IMDSv2 tokens on the server, a one-line setting.",
        _FREE,
        (0.5, 2),
        "data_breach",
    ),
    "lambda_concurrency": Recipe(
        "medium",
        "A function has no cap on how many copies run at once",
        "Like a tap with no shut-off valve.",
        "A traffic spike, bug or abuse can scale it up without limit, running up the "
        "bill and starving other functions.",
        "Set a reserved concurrency limit that fits the expected traffic.",
        _FREE,
        (0.5, 1),
        "runaway_bill",
    ),
    "cloudtrail_present": Recipe(
        "high",
        "The code doesn't set up a long-term record of who did what",
        "Like a building that throws its sign-in sheet away after 90 days.",
        "AWS keeps 90 days of account changes by default. Without a trail, nothing older is "
        "kept and file-level access isn't recorded, so an investigation could come up short. "
        "A trail may already exist outside this code, so check first.",
        "If no trail exists yet, turn one on that writes to a locked-down bucket.",
        (Component("cloudtrail_trail"),),
        (1, 2),
        "slow_detection",
    ),
    "cloudtrail_log_validation": Recipe(
        "low",
        "The audit log could be edited without anyone noticing",
        "Like a sign-in sheet written in pencil.",
        "An intruder could change the log to hide their tracks.",
        "Turn on log file validation, a single setting.",
        _FREE,
        (0.25, 0.5),
        "slow_detection",
    ),
    "lambda_secret_env": Recipe(
        "high",
        "Passwords or keys are stored in a function's settings",
        "Like taping the alarm code next to the keypad.",
        "Anyone who can view the function's settings can read the secret.",
        "Move the secret to AWS Secrets Manager and have the function read it at start-up.",
        (Component("secret"),),
        (2, 6),
        "data_breach",
    ),
    "apigw_throttling": Recipe(
        "medium",
        "The API has no request limit of its own",
        "Like a shop door that only the whole mall's crowd limit applies to.",
        "Only AWS's account-wide default limit applies, so a flood of requests can "
        "run up the bill or crowd out other APIs in the account.",
        "Set request rate and burst limits on the API.",
        _FREE,
        (0.5, 1),
        "runaway_bill",
    ),
    "sns_encryption": Recipe(
        "medium",
        "Notification messages aren't encrypted while stored",
        "Like sending postcards instead of sealed letters.",
        "Messages waiting to be delivered are stored readable.",
        "Turn on encryption with the AWS-managed key, which has no monthly charge.",
        _FREE,
        (0.25, 1),
        "data_breach",
    ),
    "rds_backup_retention": Recipe(
        "medium",
        "The database keeps a day of backups or less",
        "Like a security camera that records over yesterday's footage.",
        "A problem noticed after a day can't be undone from backup.",
        "Keep backups for 7 days or more.",
        (Component("backup_storage"),),
        (0.25, 0.5),
        "data_loss",
    ),
    "rds_deletion_protection": Recipe(
        "medium",
        "The database can be deleted by one mistake",
        'Like a delete button with no "are you sure?".',
        "One wrong command or deploy can remove the database.",
        "Turn on deletion protection, a single setting.",
        _FREE,
        (0.1, 0.25),
        "data_loss",
    ),
    "apigw_access_logging": Recipe(
        "medium",
        "The API doesn't keep a log of requests",
        "Like a shop with no receipts.",
        "During an incident or a customer complaint there's no record of what was called, by whom.",
        "Turn on access logging to CloudWatch Logs with a retention period.",
        (Component("log_ingestion"),),
        (0.5, 1),
        "slow_detection",
    ),
    "cloudfront_logging": Recipe(
        "low",
        "The website's front door doesn't keep a visitor log",
        "Like a shop with no door counter or cameras.",
        "Attacks and outages are harder to investigate after the fact.",
        "Turn on CloudFront standard logging to a log bucket.",
        (Component("log_storage"),),
        (0.5, 1),
        "slow_detection",
    ),
    "cloudfront_waf": Recipe(
        "high",
        "The website has no web application firewall",
        "Like a building with no security guard at the entrance.",
        "Common attacks and bot traffic go straight to the servers behind it.",
        "Put an AWS WAF web ACL with AWS's managed rule groups in front of it.",
        (Component("waf_web_acl"),),
        (1, 3),
        "data_breach",
    ),
}

# Older reports were saved before findings carried their concern. Their
# rule findings are matched by title instead; titles come from fixed text
# in the rule engine and trivy_checks.py, so they're stable.
_LEGACY_TITLES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), concern)
    for pattern, concern in (
        (r"^Public access to S3 bucket '.*' is not fully blocked$", "s3_public_access"),
        (r"^S3 bucket '.*' has no aws_s3_bucket_public_access_block", "s3_public_access"),
        (r"^S3 bucket '.*' has no server-side encryption", "s3_encryption"),
        (r"^S3 bucket '.*' does not have versioning enabled$", "s3_versioning"),
        (r"^S3 bucket '.*' has a bucket policy that allows anyone", "s3_public_policy"),
        (r"^Security group rule '.*' allows .* ingress to sensitive port", "sg_open_ingress"),
        (r"^Security group '.*' allows SSH or RDP from anywhere$", "sg_admin_ingress"),
        (r"^Subnet '.*' (auto-assigns public IPs|gives instances a public IP)", "subnet_public_ip"),
        (r"^EBS volume '.*' is not encrypted$", "ebs_encryption"),
        (
            r"^RDS instance '.*' (does not have storage_encrypted|does not encrypt)",
            "rds_encryption",
        ),
        (r"^RDS instance '.*' is publicly accessible$", "rds_public"),
        (r"^RDS instance '.*' is not configured multi_az$", "rds_multi_az"),
        (r"^DynamoDB table '.*' does not have point-in-time recovery", "dynamodb_pitr"),
        (r"^IAM policy '.*' grants wildcard", "iam_wildcard"),
        (r"^IAM role '.*' assume-role policy has no external-id", "iam_trust"),
        (r"^IAM role '.*' is used by running code and has ", "iam_compute_broad_managed"),
        (r" does not require IMDSv2 tokens$", "ec2_imdsv2"),
        (r"^Lambda function '.*' has no reserved_concurrent_executions", "lambda_concurrency"),
        (r"^No aws_cloudtrail resource found", "cloudtrail_present"),
        (r"^CloudTrail '.*' does not have log file validation", "cloudtrail_log_validation"),
        (r"^Lambda function '.*' has secret-like environment variables", "lambda_secret_env"),
        (
            r"^API Gateway stage\(s\) present with no aws_api_gateway_method_settings",
            "apigw_throttling",
        ),
        (r"^SNS topic '.*' is not encrypted$", "sns_encryption"),
        (r"^RDS instance '.*' keeps backups for one day or less$", "rds_backup_retention"),
        (r"^RDS instance '.*' has no deletion protection$", "rds_deletion_protection"),
        (r"^API Gateway stage '.*' has no access logging$", "apigw_access_logging"),
        (r"^CloudFront distribution '.*' has no access logging$", "cloudfront_logging"),
        (r"^CloudFront distribution '.*' has no WAF", "cloudfront_waf"),
    )
)


def infer_concern(title: str) -> str | None:
    """The concern of a rule finding saved without one, from its title."""
    for pattern, concern in _LEGACY_TITLES:
        if pattern.search(title):
            return concern
    return None
