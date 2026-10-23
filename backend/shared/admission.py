"""Atomic estimated-cost admission shared by every paid review path.

Reservations are conservative estimates, not an AWS billing ceiling. Ambiguous
failures retain their allowance; a failure known to happen before any paid call
can release it (release_operation). The caller supplies an idempotent claim in
the same transaction; no paid work may happen before that transaction succeeds.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from backend.shared.clients import DynamoDBClient, DynamoDBTransactionClient, TransactionCanceled
from backend.shared.retention import review_expires_at, review_is_live


class AdmissionDenied(Exception):
    def __init__(self, code: str = "paid_limit_reached"):
        self.code = code
        super().__init__(code)


def positive_setting(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        raise AdmissionDenied("admission_unavailable") from None
    if value <= 0:
        raise AdmissionDenied("paid_limit_reached")
    return value


def request_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def budget_actions(
    review: dict,
    cost: int,
    *,
    count_request: bool = True,
    now: float | None = None,
    table_name: str | None = None,
) -> list[dict]:
    """Conditional updates; append to the transaction containing the operation claim."""
    now = time.time() if now is None else now
    if not review_is_live(review, now) or cost < 0:
        raise AdmissionDenied("review_not_found")
    table_name = table_name or os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    if not table_name:
        raise AdmissionDenied("admission_unavailable")
    day = datetime.fromtimestamp(now, UTC).strftime("%Y%m%d")
    visitor = review.get("visitorKey", "legacy")
    actions = []
    for key, budget_name, default_budget, count_name, default_count, expiry in _public_scopes(
        review, visitor, day, now
    ):
        budget = positive_setting(budget_name, default_budget)
        if cost > budget:
            raise AdmissionDenied()
        condition = "(attribute_not_exists(spent) OR spent <= :room)"
        values = {":zero": 0, ":cost": cost, ":room": budget - cost, ":ttl": expiry}
        update = "SET spent = if_not_exists(spent, :zero) + :cost, #ttl = if_not_exists(#ttl, :ttl)"
        if count_request:
            maximum = positive_setting(count_name, default_count)
            condition += " AND (attribute_not_exists(requests) OR requests < :maximum)"
            update += ", requests = if_not_exists(requests, :zero) + :one"
            values.update({":one": 1, ":maximum": maximum})
        actions.append(
            {
                "Update": {
                    "TableName": table_name,
                    "Key": {"counterKey": key},
                    "UpdateExpression": update,
                    "ConditionExpression": condition,
                    "ExpressionAttributeNames": {"#ttl": "ttl"},
                    "ExpressionAttributeValues": values,
                }
            }
        )
    return actions


def _public_scopes(review: dict, visitor: str, day: str, now: float) -> list[tuple]:
    return [
        (
            f"paid#global#{day}",
            "PAID_DAILY_BUDGET_MICRO_USD",
            1_000_000,
            "PAID_DAILY_MAX_REQUESTS",
            100,
            int(now) + 172800,
        ),
        (
            f"paid#visitor#{visitor}#{day}",
            "PAID_VISITOR_BUDGET_MICRO_USD",
            1_000_000,
            "PAID_VISITOR_MAX_REQUESTS",
            30,
            int(now) + 172800,
        ),
        (
            f"paid#review#{review['reviewId']}",
            "PAID_REVIEW_BUDGET_MICRO_USD",
            1_000_000,
            "PAID_REVIEW_MAX_REQUESTS",
            20,
            review_expires_at(review),
        ),
    ]


def reserve_operation(review: dict, operation: str, payload: Any, cost: int) -> bool:
    """True for a new claim; False for a digest-identical retry. No automatic refund.

    Retrying an existing claim is permitted only for intrinsically idempotent
    dispatch (same Standard execution name/input or the same one-use task token).
    Other callers must serve their saved result or return in-progress.
    """
    table_name = os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    if not table_name or not review_is_live(review):
        raise AdmissionDenied("admission_unavailable")
    key = {"counterKey": f"operation#{review['reviewId']}#{operation}"}
    digest = request_digest(payload)
    day = datetime.now(UTC).strftime("%Y%m%d")
    table = DynamoDBClient(table_name=table_name)
    existing = table.get_item(key)
    if existing:
        if existing.get("day") != day:
            raise AdmissionDenied("operation_expired")
        if existing.get("digest") != digest:
            raise AdmissionDenied("operation_conflict")
        return False
    budget = budget_actions(review, cost)
    actions = [
        {
            "Put": {
                "TableName": table_name,
                "Item": {
                    **key,
                    "digest": digest,
                    "day": day,
                    "ttl": review_expires_at(review),
                    "cost": cost,
                    # What release_operation must give back.
                    "counterKeys": [a["Update"]["Key"]["counterKey"] for a in budget],
                    "requestKeys": [
                        a["Update"]["Key"]["counterKey"]
                        for a in budget
                        if ":one" in a["Update"]["ExpressionAttributeValues"]
                    ],
                },
                "ConditionExpression": "attribute_not_exists(counterKey)",
            }
        },
        *budget,
    ]
    try:
        DynamoDBTransactionClient().transact_write(actions)
    except TransactionCanceled as exc:
        # A duplicate can be retried by its caller. Never authorize from a
        # cancellation whose cause is unknown or a racing preliminary read.
        if exc.reasons and exc.reasons[0] == "ConditionalCheckFailed":
            raise AdmissionDenied("operation_in_progress") from None
        raise AdmissionDenied() from None
    return True


def release_operation(review_id: str, operation: str) -> bool:
    """Give back a claim's reservation, at most once.

    Only for failures known to happen before any paid call (paused, rejected
    input). The claim itself stays, so the operation can't be
    dispatched again. True if this call released it.
    """
    table_name = os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    if not table_name:
        return False
    key = {"counterKey": f"operation#{review_id}#{operation}"}
    claim = DynamoDBClient(table_name=table_name).get_item(key, consistent=True)
    if not claim or claim.get("released") or "counterKeys" not in claim:
        return False
    cost = int(claim.get("cost", 0))
    request_keys = set(claim.get("requestKeys", []))
    actions: list[dict] = [
        {
            "Update": {
                "TableName": table_name,
                "Key": key,
                "UpdateExpression": "SET released = :yes",
                "ConditionExpression": "attribute_exists(counterKey) AND attribute_not_exists(released)",
                "ExpressionAttributeValues": {":yes": True},
            }
        }
    ]
    for counter in claim["counterKeys"]:
        update = "SET spent = spent - :cost"
        values: dict[str, Any] = {":cost": cost}
        if counter in request_keys:
            update += ", requests = requests - :one"
            values[":one"] = 1
        actions.append(
            {
                "Update": {
                    "TableName": table_name,
                    "Key": {"counterKey": counter},
                    "UpdateExpression": update,
                    "ConditionExpression": "attribute_exists(spent)",
                    "ExpressionAttributeValues": values,
                }
            }
        )
    try:
        DynamoDBTransactionClient().transact_write(actions)
    except TransactionCanceled:
        return False
    return True
