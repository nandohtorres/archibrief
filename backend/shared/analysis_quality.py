"""Small public quality counters; never publish rejected text or error details.

Lifecycle completion means the pipeline stopped successfully. These counters
describe retained output, not semantic correctness or architecture coverage.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

OUTCOMES = {"complete", "partial", "rules-only", "all-rejected", "no-findings", "unknown"}
REASONS = {
    "model_verification_rejected",
    "schema_validation_rejected",
    "quality_not_recorded",
    "model_unavailable",
}


def stage_counts(attempted: int, accepted: int) -> dict[str, int]:
    if not 0 <= accepted <= attempted:
        raise ValueError("invalid analysis stage counts")
    return {"attempted": attempted, "accepted": accepted, "rejected": attempted - accepted}


def _counts(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    keys = ("attempted", "accepted", "rejected")
    if not all(
        type(value.get(key)) in (int, Decimal)
        and 0 <= value[key] <= 10000
        and value[key] == int(value[key])
        for key in keys
    ):
        return None
    if value["attempted"] != value["accepted"] + value["rejected"]:
        return None
    return {key: int(value[key]) for key in keys}


def build_analysis_quality(
    model_output: Any, candidates: list[dict], valid: list[dict], *, model_unavailable: bool = False
) -> dict[str, Any]:
    """model_unavailable: the model step failed (timed out, errored) and
    the report holds only the deterministic findings."""
    if model_unavailable:
        model_output = stage_counts(0, 0)
    model = _counts(model_output)
    validation = stage_counts(len(candidates), len(valid))
    reasons = ["model_unavailable"] if model_unavailable else []
    if model and model["rejected"]:
        reasons.append("model_verification_rejected")
    if validation["rejected"]:
        reasons.append("schema_validation_rejected")
    if model is None:
        reasons.append("quality_not_recorded")
        outcome = "partial" if validation["rejected"] else "unknown"
    elif model_unavailable:
        outcome = "rules-only" if valid else "no-findings"
    elif not valid:
        outcome = "all-rejected" if reasons else "no-findings"
    elif not any(f.get("model_id") for f in valid):
        outcome = "rules-only"
    else:
        outcome = "partial" if reasons else "complete"
    return {
        "version": 1,
        "outcome": outcome,
        "model_verification": model,
        "schema_validation": validation,
        "reason_codes": reasons,
    }


def public_analysis_quality(value: Any) -> dict[str, Any]:
    """Allowlist persisted metadata. Older or invalid metadata stays unknown."""
    unknown = {
        "version": 1,
        "outcome": "unknown",
        "model_verification": None,
        "schema_validation": None,
        "reason_codes": ["quality_not_recorded"],
    }
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or not isinstance(value.get("outcome"), str)
        or value["outcome"] not in OUTCOMES
    ):
        return unknown
    model = _counts(value.get("model_verification"))
    validation = _counts(value.get("schema_validation"))
    if validation is None or (model is None and value["outcome"] not in {"unknown", "partial"}):
        return unknown
    reasons = value.get("reason_codes")
    return {
        "version": 1,
        "outcome": value["outcome"],
        "model_verification": model,
        "schema_validation": validation,
        "reason_codes": [
            code
            for code in (reasons if isinstance(reasons, list) else [])
            if isinstance(code, str) and code in REASONS
        ],
    }


def public_analysis_scope(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("version") != "terraform-observations@2026-10-23":
        return None
    fields = ("facts_emitted", "omitted_resources", "omitted_items", "incomplete_resources")
    if not all(
        type(value.get(key)) in (int, Decimal)
        and 0 <= value[key] <= 100000
        and value[key] == int(value[key])
        for key in fields
    ):
        return None
    return {
        "version": value["version"],
        **{key: int(value[key]) for key in fields},
        "truncated": bool(value["omitted_resources"] or value["omitted_items"]),
        "runtime_verified": False,
    }
