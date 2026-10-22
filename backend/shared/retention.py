"""Logical review expiry, independent of asynchronous storage cleanup.

Existing workflow records have createdAt but may lack a DynamoDB ttl. Their
seven-day lifetime is derived from that original timestamp, never from access.
Unknown or malformed lifetimes fail closed. This does not delete stored data.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

REVIEW_LIFETIME_SECONDS = 7 * 24 * 3600


def review_expires_at(item: dict[str, Any]) -> int:
    expiries = []
    try:
        if "ttl" in item:
            expiries.append(int(item["ttl"]))
        if "createdAt" in item:
            created = datetime.fromisoformat(item["createdAt"])
            if created.tzinfo is None:
                return 0
            expiries.append(int(created.timestamp()) + REVIEW_LIFETIME_SECONDS)
    except (ValueError, TypeError, OverflowError, OSError):
        return 0
    return min(expiries, default=0)


def review_is_live(item: dict[str, Any], now: float | None = None) -> bool:
    return review_expires_at(item) > (time.time() if now is None else now)
