"""AWS list prices for the things a fix usually adds, so the stakeholder
view can say what a fix costs per month.

Prices are us-east-1, on-demand, Linux, in US dollars per month (730
hours), as listed by AWS in October 2026. They are a starting estimate:
a real bill also depends on region, discounts, traffic and storage.
Dollar amounts always come from this table, never from the model: the
model can only name an item below (and a size), and this code prices it.

An item whose cost depends on usage nobody knows from the code (log
volume, table size) has no fixed price. It carries a `usage_note`
saying what it costs per unit, and its monthly high is None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PRICES_AS_OF = "2026-10"
PRICE_REGION = "us-east-1"
HOURS_PER_MONTH = 730

_EC2_URL = "https://aws.amazon.com/ec2/pricing/on-demand/"
_RDS_URL = "https://aws.amazon.com/rds/mysql/pricing/"
_AURORA_URL = "https://aws.amazon.com/rds/aurora/pricing/"

# On-demand hourly rates. A size missing here is priced as unknown,
# never guessed.
EC2_HOURLY: dict[str, float] = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t4g.micro": 0.0084,
    "t4g.small": 0.0168,
    "t4g.medium": 0.0336,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m6i.large": 0.096,
    "c5.large": 0.085,
    "r5.large": 0.126,
}

# RDS for MySQL single-AZ rates; PostgreSQL is a few percent higher.
RDS_HOURLY: dict[str, float] = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t3.large": 0.136,
    "db.t4g.micro": 0.016,
    "db.t4g.small": 0.032,
    "db.t4g.medium": 0.065,
    "db.m5.large": 0.171,
    "db.m6g.large": 0.152,
    "db.r5.large": 0.24,
    "db.r6g.large": 0.215,
}

AURORA_HOURLY: dict[str, float] = {
    "db.t3.medium": 0.082,
    "db.t4g.medium": 0.073,
    "db.r5.large": 0.29,
    "db.r6g.large": 0.26,
}

# ElastiCache for Redis OSS on-demand node rates (standard support, not
# extended support), from the AWS Price List API offer published
# 2026-10-14.
ELASTICACHE_HOURLY: dict[str, float] = {
    "cache.t3.micro": 0.017,
    "cache.t3.small": 0.034,
    "cache.t3.medium": 0.068,
    "cache.t4g.micro": 0.016,
    "cache.t4g.small": 0.032,
    "cache.t4g.medium": 0.065,
    "cache.m6g.large": 0.149,
    "cache.m7g.large": 0.158,
    "cache.r6g.large": 0.206,
    "cache.r7g.large": 0.219,
}

_SIZE = re.compile(r"^(db\.|cache\.)?[a-z][a-z0-9-]*\.[a-z0-9]+$")


@dataclass(frozen=True)
class PriceItem:
    label: str
    # Fixed monthly price per unit, or None when it's priced by size or usage.
    monthly: float | None
    source_url: str
    usage_note: str | None = None
    # Which hourly table prices this item by size.
    sized_by: dict[str, float] | None = None


PRICE_ITEMS: dict[str, PriceItem] = {
    "none": PriceItem("Configuration change only", 0.0, ""),
    "alb": PriceItem(
        "Application Load Balancer",
        # $0.0225/hour plus about one LCU ($0.008/hour) of light traffic.
        round((0.0225 + 0.008) * HOURS_PER_MONTH, 2),
        "https://aws.amazon.com/elasticloadbalancing/pricing/",
    ),
    "ec2_instance": PriceItem("Extra server", None, _EC2_URL, sized_by=EC2_HOURLY),
    "rds_standby": PriceItem(
        "Standby database copy (Multi-AZ)", None, _RDS_URL, sized_by=RDS_HOURLY
    ),
    "aurora_replica": PriceItem(
        "Aurora replica in another zone", None, _AURORA_URL, sized_by=AURORA_HOURLY
    ),
    "cache_replica": PriceItem(
        "ElastiCache replica node",
        None,
        "https://aws.amazon.com/elasticache/pricing/",
        sized_by=ELASTICACHE_HOURLY,
    ),
    "nat_gateway": PriceItem(
        "NAT gateway",
        round(0.045 * HOURS_PER_MONTH, 2),
        "https://aws.amazon.com/vpc/pricing/",
        usage_note="plus $0.045 per GB it processes",
    ),
    "interface_endpoint": PriceItem(
        "Private VPC endpoint (per zone)",
        round(0.01 * HOURS_PER_MONTH, 2),
        "https://aws.amazon.com/privatelink/pricing/",
        usage_note="plus $0.01 per GB it processes",
    ),
    "gateway_endpoint": PriceItem(
        "S3/DynamoDB gateway endpoint", 0.0, "https://aws.amazon.com/vpc/pricing/"
    ),
    "kms_key": PriceItem(
        "Customer-managed encryption key",
        1.0,
        "https://aws.amazon.com/kms/pricing/",
        usage_note="plus $0.03 per 10,000 requests",
    ),
    "secret": PriceItem(
        "Secrets Manager secret",
        0.40,
        "https://aws.amazon.com/secrets-manager/pricing/",
        usage_note="plus $0.05 per 10,000 requests",
    ),
    "waf_web_acl": PriceItem(
        "Web application firewall (3 managed rule groups)",
        # $5 per web ACL plus $1 per rule group.
        8.0,
        "https://aws.amazon.com/waf/pricing/",
        usage_note="plus $0.60 per million requests",
    ),
    "shield_advanced": PriceItem(
        "AWS Shield Advanced",
        3000.0,
        "https://aws.amazon.com/shield/pricing/",
        usage_note="with a one-year commitment, plus data transfer fees; one "
        "subscription covers the whole organization",
    ),
    "detailed_monitoring": PriceItem(
        "1-minute server monitoring",
        # About 7 metrics at $0.30 each.
        2.10,
        "https://aws.amazon.com/cloudwatch/pricing/",
    ),
    "cloudtrail_trail": PriceItem(
        "CloudTrail audit log",
        None,
        "https://aws.amazon.com/cloudtrail/pricing/",
        usage_note="the first trail of management events is free; you pay S3 storage "
        "for the log files, usually a few dollars a month",
    ),
    "log_ingestion": PriceItem(
        "Access logs",
        None,
        "https://aws.amazon.com/cloudwatch/pricing/",
        usage_note="$0.50 per GB of logs written",
    ),
    "log_storage": PriceItem(
        "Log files in S3",
        None,
        "https://aws.amazon.com/s3/pricing/",
        usage_note="$0.023 per GB of log files kept",
    ),
    "s3_old_versions": PriceItem(
        "Storage for old file versions",
        None,
        "https://aws.amazon.com/s3/pricing/",
        usage_note="$0.023 per GB of old versions kept",
    ),
    "pitr_storage": PriceItem(
        "Point-in-time recovery",
        None,
        "https://aws.amazon.com/dynamodb/pricing/",
        usage_note="$0.20 per GB of table data per month",
    ),
    "backup_storage": PriceItem(
        "Extra backup storage",
        None,
        _RDS_URL,
        usage_note="free up to the size of the database, then $0.095 per GB",
    ),
}

# What the model may name in a fix's components (reason.py's schema).
PRICE_ITEM_KEYS = tuple(PRICE_ITEMS)


@dataclass(frozen=True)
class PricedLine:
    label: str
    monthly_low: float
    # None: depends on usage, or on a size this table doesn't list.
    monthly_high: float | None
    basis: str
    source_url: str

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "monthly_low": self.monthly_low,
            "monthly_high": self.monthly_high,
            "basis": self.basis,
            "source_url": self.source_url,
        }


def price_line(item_key: str, quantity: int = 1, size: str | None = None) -> PricedLine:
    """One fix component's monthly cost. Unknown items and sizes are
    reported as unknown, never estimated."""
    item = PRICE_ITEMS.get(item_key)
    if item is None:
        return PricedLine("Unpriced item", 0.0, None, "not in ArchiBrief's price table", "")
    quantity = max(1, int(quantity))
    label = item.label if quantity == 1 else f"{item.label} ×{quantity}"

    if item.sized_by is not None:
        rate = item.sized_by.get(size or "") if size and _SIZE.match(size) else None
        if rate is None:
            basis = (
                f"depends on the size ({size}), which isn't in the price table"
                if size and _SIZE.match(size)
                else "depends on the size, which couldn't be read from the code"
            )
            return PricedLine(label, 0.0, None, basis, item.source_url)
        monthly = round(rate * HOURS_PER_MONTH * quantity, 2)
        return PricedLine(
            label, monthly, monthly, f"{size} at ${rate}/hour, on-demand", item.source_url
        )

    if item.monthly is None:
        return PricedLine(label, 0.0, None, item.usage_note or "depends on usage", item.source_url)

    monthly = round(item.monthly * quantity, 2)
    basis = "list price" if monthly else "no AWS charge"
    if item.usage_note:
        basis = f"{basis}, {item.usage_note}"
    return PricedLine(label, monthly, monthly, basis, item.source_url)
