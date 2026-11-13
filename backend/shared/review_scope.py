"""The P0 review scope record: what was declared, and what the AI was sent.

Ingest builds a *pending* record (counts and identities only); the worker
turns it into a *final* record once the summary membership and the model
outcome are known; Finalize copies the final record into the evidence
ledger, which is the authoritative copy (P0 contract, section 5).

Pure data rules only: no HCL, no AWS clients. Nothing here is user-facing
in P0 and an invalid record never blocks a review.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

RECORD_VERSION = "review_scope@1"
MAX_DECLARATIONS = 1000
MAX_GAPS = 100
MAX_ADDRESS_LENGTH = 512
# Contract rule 2: identifiers are letters, digits, "_" or "-", dot-joined.
ADDRESS_PATTERN = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")

# The resource summary keeps only types matching this pattern; a declared
# type that fails it is `other/summary_filtered`. resource_summary imports
# it from here so the two can't drift.
SUMMARY_RESOURCE_TYPE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

STATES = frozenset({"recorded", "unknown_root", "malformed"})
OUTCOMES = frozenset({"completed", "not_invoked", "unknown"})
CATEGORIES = ("reviewed", "zero_copy", "unsupported", "other")
OTHER_REASONS = frozenset(
    {"summary_cap", "summary_filtered", "not_retained", "model_not_invoked", "outcome_unknown"}
)
GAP_REASONS = frozenset(
    {
        "remote_source",
        "source_unresolved",
        "source_missing",
        "source_outside_archive",
        "count_unresolved",
        "count_not_singleton",
        "for_each_unsupported",
        "cycle",
        "depth_limit",
        "expansion_limit",
    }
)
WARNINGS = frozenset({"skipped_tf_json"})

_DECLARATION_KEYS = frozenset(
    {
        "address",
        "type",
        "parsed_key",
        "instances",
        "retained",
        "in_summary",
        "sent",
        "category",
        "reason",
    }
)
_RECORD_KEYS = frozenset(
    {
        "version",
        "status",
        "state",
        "known_y",
        "count_complete",
        "model_outcome",
        "x",
        "sent_count",
        "categories",
        "declarations",
        "module_gaps",
        "gaps_complete",
        "warnings",
    }
)


def is_aws_type(resource_type: str) -> bool:
    return resource_type.startswith("aws_")


def new_declaration(
    address: str, resource_type: str, parsed_key: str, instances: int | None, retained: bool
) -> dict:
    """One pending declaration entry."""
    return {
        "address": address,
        "type": resource_type,
        "parsed_key": parsed_key,
        "instances": instances,
        "retained": retained,
        "in_summary": None,
        "sent": None,
        "category": None,
        "reason": None,
    }


def pending_record(
    state: str,
    declarations: list[dict] | None = None,
    module_gaps: list[dict] | None = None,
    *,
    count_complete: bool = True,
    gaps_complete: bool = True,
    warnings: Iterable[str] = (),
) -> dict:
    """The record Ingest writes into parsed/<review_id>.json."""
    recorded = state == "recorded"
    declarations = list(declarations or []) if recorded else []
    return {
        "version": RECORD_VERSION,
        "status": "pending",
        "state": state,
        "known_y": len(declarations) if recorded else None,
        "count_complete": count_complete if recorded else False,
        "model_outcome": None,
        "x": None,
        "sent_count": None,
        # Null, not zero: nothing is categorized until finalize. Zero would
        # claim "counted, none found" (same rule as x and sent_count).
        "categories": dict.fromkeys(CATEGORIES),
        "declarations": declarations,
        "module_gaps": list(module_gaps or []) if recorded else [],
        "gaps_complete": gaps_complete if recorded else True,
        "warnings": sorted(set(warnings)),
    }


def _categorize(entry: dict, in_summary: bool, outcome: str) -> tuple[str, str | None]:
    """Category first match wins: zero_copy, unsupported, reviewed, other."""
    if entry["instances"] == 0:
        return "zero_copy", None
    if not is_aws_type(entry["type"]):
        return "unsupported", None
    if in_summary and outcome == "completed":
        return "reviewed", None
    if not in_summary:
        if not entry["retained"]:
            return "other", "not_retained"
        if not SUMMARY_RESOURCE_TYPE.fullmatch(entry["type"]):
            return "other", "summary_filtered"
        return "other", "summary_cap"
    return "other", "model_not_invoked" if outcome == "not_invoked" else "outcome_unknown"


def _sent(in_summary: bool, outcome: str) -> bool | None:
    if outcome == "completed":
        return in_summary
    if outcome == "not_invoked" or not in_summary:
        return False
    return None  # in the summary, invocation started then failed: unknown


def finalize_scope(
    pending: dict,
    summary_members: Iterable[Iterable[str]] | None,
    model_outcome: str,
) -> dict:
    """Apply summary membership and the model outcome to a pending record.

    Returns a new record with status "final"; `pending` is not modified.
    """
    if model_outcome not in OUTCOMES:
        raise ValueError("unknown model outcome")
    final = {
        **pending,
        "status": "final",
        "model_outcome": model_outcome,
        # Null unless recorded: an unknown scope was never counted.
        "categories": dict.fromkeys(CATEGORIES, None if pending.get("state") != "recorded" else 0),
        "declarations": [],
        "module_gaps": [dict(gap) for gap in pending.get("module_gaps", [])],
        "warnings": list(pending.get("warnings", [])),
    }
    if pending.get("state") != "recorded":
        return final
    if summary_members is None:
        raise ValueError("a recorded scope needs the summary membership")
    members = {tuple(pair) for pair in summary_members}
    for entry in pending["declarations"]:
        in_summary = (entry["type"], entry["parsed_key"]) in members
        category, reason = _categorize(entry, in_summary, model_outcome)
        final["declarations"].append(
            {
                **entry,
                "in_summary": in_summary,
                "sent": _sent(in_summary, model_outcome),
                "category": category,
                "reason": reason,
            }
        )
        final["categories"][category] += 1
    if model_outcome == "unknown":
        final["x"] = final["sent_count"] = None
    else:
        final["x"] = final["categories"]["reviewed"]
        final["sent_count"] = sum(1 for d in final["declarations"] if d["sent"] is True)
    return final


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _declaration_errors(entry: object, index: int, status: str, outcome: str | None) -> list[str]:
    where = f"declarations[{index}]"
    if not isinstance(entry, dict) or set(entry) != _DECLARATION_KEYS:
        return [f"{where}: wrong keys"]
    errors: list[str] = []
    for key in ("address", "type", "parsed_key"):
        if not isinstance(entry[key], str) or not entry[key]:
            errors.append(f"{where}.{key}: must be a non-empty string")
    if isinstance(entry["address"], str) and len(entry["address"]) > MAX_ADDRESS_LENGTH:
        errors.append(f"{where}.address: too long")
    elif isinstance(entry["address"], str) and not ADDRESS_PATTERN.fullmatch(entry["address"]):
        errors.append(f"{where}.address: invalid characters")
    instances = entry["instances"]
    if instances is not None and not (_is_int(instances) and 0 <= instances <= MAX_DECLARATIONS):
        errors.append(f"{where}.instances: must be null or 0..{MAX_DECLARATIONS}")
    if not isinstance(entry["retained"], bool):
        errors.append(f"{where}.retained: must be a boolean")
    if status == "pending":
        if any(entry[k] is not None for k in ("in_summary", "sent", "category", "reason")):
            errors.append(f"{where}: pending entries carry no outcome fields")
        return errors
    if not isinstance(entry["in_summary"], bool):
        errors.append(f"{where}.in_summary: must be a boolean")
        return errors
    if errors or outcome not in OUTCOMES:
        return errors
    category, reason = _categorize(entry, entry["in_summary"], outcome)
    if (entry["category"], entry["reason"]) != (category, reason):
        errors.append(f"{where}: category/reason disagree with membership and outcome")
    if entry["sent"] != _sent(entry["in_summary"], outcome) or (
        entry["sent"] is None and outcome != "unknown"
    ):
        errors.append(f"{where}.sent: disagrees with membership and outcome")
    return errors


def _gap_errors(gaps: object) -> list[str]:
    if not isinstance(gaps, list) or len(gaps) > MAX_GAPS:
        return [f"module_gaps: must be a list of at most {MAX_GAPS}"]
    errors: list[str] = []
    for index, gap in enumerate(gaps):
        if (
            not isinstance(gap, dict)
            or set(gap) != {"address", "reasons"}
            or not isinstance(gap["address"], str)
            or not 0 < len(gap["address"]) <= MAX_ADDRESS_LENGTH
            or not isinstance(gap["reasons"], list)
            or not gap["reasons"]
            or not set(gap["reasons"]) <= GAP_REASONS
        ):
            errors.append(f"module_gaps[{index}]: invalid")
    return errors


def validate_scope(record: object) -> list[str]:
    """Every problem with a record; [] means valid. Never raises."""
    try:
        return _validate(record)
    except Exception as exc:  # noqa: BLE001 - a validator must not take the review down
        return [f"validator error: {type(exc).__name__}"]


def _validate(record: object) -> list[str]:
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        return ["record: wrong keys"]
    errors: list[str] = []
    status, state, outcome = record["status"], record["state"], record["model_outcome"]
    if record["version"] != RECORD_VERSION:
        errors.append("version: unsupported")
    if status not in ("pending", "final"):
        errors.append("status: must be pending or final")
    if state not in STATES:
        errors.append("state: unknown")
    for key in ("count_complete", "gaps_complete"):
        if not isinstance(record[key], bool):
            errors.append(f"{key}: must be a boolean")
    warnings = record["warnings"]
    if not isinstance(warnings, list) or not set(warnings) <= WARNINGS:
        errors.append("warnings: unknown value")
    categories = record["categories"]
    if not isinstance(categories, dict) or set(categories) != set(CATEGORIES):
        return [*errors, "categories: invalid"]
    # Never mixed: counts are all ints only on a final recorded scope;
    # otherwise nothing was counted and they are all null.
    if status == "final" and state == "recorded":
        if not all(_is_int(v) and v >= 0 for v in categories.values()):
            return [*errors, "categories: invalid"]
    elif any(v is not None for v in categories.values()):
        return [*errors, "categories: must be null until a recorded scope is final"]
    if status == "pending":
        if any(record[k] is not None for k in ("model_outcome", "x", "sent_count")):
            errors.append("pending: model_outcome, x and sent_count must be null")
    elif outcome not in OUTCOMES:
        errors.append("model_outcome: unknown")
    declarations = record["declarations"]
    if not isinstance(declarations, list) or len(declarations) > MAX_DECLARATIONS:
        return [*errors, f"declarations: must be a list of at most {MAX_DECLARATIONS}"]
    errors.extend(_gap_errors(record["module_gaps"]))

    if state != "recorded":
        if record["known_y"] is not None or declarations or record["module_gaps"]:
            errors.append(f"{state}: carries no counts")
        if record["x"] is not None or record["sent_count"] is not None:
            errors.append(f"{state}: x, sent_count and categories must be empty")
        return errors

    if not _is_int(record["known_y"]) or record["known_y"] != len(declarations):
        errors.append("known_y: must equal the number of declarations")
    for index, entry in enumerate(declarations):
        errors.extend(_declaration_errors(entry, index, status, outcome))
    keys = [(d.get("type"), d.get("parsed_key")) for d in declarations if isinstance(d, dict)]
    if len(set(keys)) != len(keys):
        errors.append("declarations: (type, parsed_key) must be unique")
    addresses = [d.get("address") for d in declarations if isinstance(d, dict)]
    if len(set(addresses)) != len(addresses):
        errors.append("declarations: addresses must be unique")
    if status == "pending" or errors:
        return errors

    counted = dict.fromkeys(CATEGORIES, 0)
    for entry in declarations:
        counted[entry["category"]] += 1
    if counted != categories:
        errors.append("categories: do not match the declarations")
    if sum(categories.values()) != record["known_y"]:
        errors.append("invariant: reviewed + zero_copy + unsupported + other != Y")
    if outcome == "unknown":
        if record["x"] is not None or record["sent_count"] is not None:
            errors.append("unknown outcome: x and sent_count must be null")
    else:
        if record["x"] != categories["reviewed"]:
            errors.append("x: must equal the reviewed count")
        if record["sent_count"] != sum(1 for d in declarations if d["sent"] is True):
            errors.append("sent_count: must equal the entries sent")
    return errors
