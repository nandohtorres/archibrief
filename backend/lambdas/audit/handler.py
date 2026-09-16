"""ArchiBrief Lambda: audit.

Records inputs, defaults applied, and Guardrails decisions for one review
execution (ADR-0022 layer 4) — the traceability record, separate from the
evidence ledger itself (Finalize). The DynamoDB write goes through
backend.shared.clients.DynamoDBClient, which cannot succeed without a
deployed table (Work-Project-Deployment-Roadmap.md AWS-account blocker),
but the record shape and logic here are real and independently testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.shared.clients import DynamoDBClient


@dataclass
class AuditLogEntry:
    review_id: str
    baseline_answers: dict[str, str]
    guardrails_decisions: list[dict[str, Any]]
    deterministic_rule_version: str | None
    corpus_version: str | None
    model_id: str | None
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_item(self) -> dict[str, Any]:
        return {
            "auditId": self.audit_id,
            "reviewId": self.review_id,
            "baselineAnswers": self.baseline_answers,
            "guardrailsDecisions": self.guardrails_decisions,
            "deterministicRuleVersion": self.deterministic_rule_version,
            "corpusVersion": self.corpus_version,
            "modelId": self.model_id,
            "createdAt": self.created_at,
        }


def build_audit_entry(event: dict) -> AuditLogEntry:
    return AuditLogEntry(
        review_id=event["review_id"],
        baseline_answers=event.get("baseline_answers", {}),
        guardrails_decisions=event.get("guardrails_decisions", []),
        deterministic_rule_version=event.get("deterministic_rule_version"),
        corpus_version=event.get("corpus_version"),
        model_id=event.get("model_id"),
    )


def handler(event, context):
    entry = build_audit_entry(event)
    table_name = event.get("audit_table_name")
    if table_name:
        DynamoDBClient(table_name=table_name).put_item(entry.to_item())
    return {"status": "recorded", "audit_id": entry.audit_id}
