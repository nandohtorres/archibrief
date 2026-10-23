"""Small public quality counters; never publish rejected text or error details.

Lifecycle completion means the pipeline stopped successfully. These counters
describe retained output, not semantic correctness or architecture coverage.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

OUTCOMES = {"complete", "partial", "rules-only", "all-rejected", "no-findings", "unknown"}
REASONS = {"model_verification_rejected", "schema_validation_rejected", "quality_not_recorded"}


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
    model_output: Any, candidates: list[dict], valid: list[dict]
) -> dict[str, Any]:
    model = _counts(model_output)
    validation = stage_counts(len(candidates), len(valid))
    reasons = []
    if model and model["rejected"]:
        reasons.append("model_verification_rejected")
    if validation["rejected"]:
        reasons.append("schema_validation_rejected")
    if model is None:
        reasons.append("quality_not_recorded")
        outcome = "partial" if validation["rejected"] else "unknown"
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
