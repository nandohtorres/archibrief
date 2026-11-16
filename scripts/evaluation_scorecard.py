"""Append numeric evaluation summaries; never import AWS or publish narratives."""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:+/-]{0,160}$")
DEV_V1 = Counter({"T3a": 1, "T1-full": 2, "T2-full": 2})


def identifier(value: object) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Expected a bounded identifier, not narrative text")
    return value


def number(value: object, *, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative number")
    if integer and type(value) is not int:
        raise ValueError("Expected an integer count")
    return value


def ratio(a, b):
    return a / b if b else None


def distribution(values):
    known = [number(v) for v in values if v is not None]
    return {
        "median": statistics.median(known) if known else None,
        "max": max(known) if known else None,
        "observed": len(known),
        "missing": len(values) - len(known),
    }


def build_rows(
    report: dict,
    existing: dict,
    *,
    round_id: str,
    case_set: str,
    role: str,
    code_revision: str | None = None,
    label: str | None = None,
    cases: list[str] | None = None,
    register_case_set=False,
) -> tuple[list[dict], dict]:
    identifier(round_id)
    identifier(case_set)
    if role not in {"candidate", "control", "baseline", "history"}:
        raise ValueError("Invalid role")
    if report.get("judging_complete") is not True:
        raise ValueError("Round judging is incomplete")
    slots = report.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("Finished report needs nonempty slots")
    selected = set(map(identifier, cases)) if cases else None
    groups = defaultdict(list)
    seen = set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise TypeError("Invalid slot")
        case = identifier(slot.get("case"))
        if selected is not None and case not in selected:
            continue
        key = slot.get("slot")
        if type(key) is not int or key in seen:
            raise ValueError("Missing or duplicate slot")
        seen.add(key)
        revision = identifier(
            slot.get("code_revision") or code_revision or report.get("code_revision")
        )
        versions = slot.get("rule_engine_versions")
        if not isinstance(versions, list) or len(versions) != 1:
            raise ValueError("Each slot needs exactly one rule engine version")
        version = identifier(versions[0])
        if slot.get("role", role) != role:
            raise ValueError("Do not mix candidate and control roles in one append")
        groups[(revision, version)].append(slot)
    if not groups:
        raise ValueError("No selected slots")
    registry = dict(existing.get("case_sets", {}))
    if case_set not in registry and not register_case_set:
        raise ValueError("New case set requires --register-case-set and a new name")
    rows = []
    for (revision, version), members in sorted(groups.items()):
        counts = Counter(s["case"] for s in members)
        if selected is not None and set(counts) != selected:
            raise ValueError("Selected case set is incomplete in a version group")
        if case_set == "dev-v1" and counts != DEV_V1:
            raise ValueError("dev-v1 requires T3a once, T1-full twice, T2-full twice")
        if case_set in registry:
            expected = registry[case_set]
            if set(counts) != set(expected["cases"]) or (
                "review_counts" in expected
                and dict(counts) != expected["review_counts"]
            ):
                raise ValueError("Case-set mismatch: use a new case_set name")
        else:
            registry[case_set] = {
                "cases": sorted(counts),
                "review_counts": dict(sorted(counts.items())),
            }
        if any(type(s.get("completed")) is not bool for s in members):
            raise ValueError("Missing completion status")
        completed = sum(s["completed"] for s in members)

        def total(field, members=members):
            return sum(number(s[field], integer=True) for s in members)

        caught, expected = total("critical_high_caught"), total("critical_high_total")
        all_caught, all_expected = total("all_caught"), total("all_total")
        if caught > expected or all_caught > all_expected:
            raise ValueError("Caught count exceeds denominator")
        findings, false, unsafe = (
            total("findings"),
            total("false_claims"),
            total("unsafe_fixes"),
        )
        if false > findings or unsafe > findings:
            raise ValueError("Finding judgment count exceeds findings")
        models = {
            identifier(s.get("model_id") or report.get("model_id")) for s in members
        }
        if len(models) != 1:
            raise ValueError("Do not mix model IDs in one version group")
        costs = [
            s.get("cost_usd") if s.get("cost_known") is True else None for s in members
        ]
        cost = distribution(costs)
        cost.update(
            total=sum(costs) if all(c is not None for c in costs) else None,
            measured=all(s.get("cost_measured") is True for s in members)
            and cost["missing"] == 0,
        )
        p3b = None
        if any(s.get("p3b") is not None for s in members):
            if any(not isinstance(s.get("p3b"), dict) for s in members):
                raise ValueError("Missing P3b metadata within enabled version group")
            p3b = {}
            for key in ("verification_calls", "findings_removed", "findings_changed"):
                p3b[key] = sum(number(s["p3b"][key], integer=True) for s in members)
            for source, target in (
                ("added_cost_usd", "added_cost_usd"),
                ("added_seconds", "added_seconds"),
            ):
                values = [s["p3b"].get(source) for s in members]
                p3b[target] = (
                    sum(number(v) for v in values)
                    if all(v is not None for v in values)
                    else None
                )
        stamp = report.get("generated_at")
        if not isinstance(stamp, str):
            raise TypeError("Finished report needs generated_at")
        day = date.fromisoformat(stamp[:10]).isoformat()
        row_id = f"{round_id}:{revision}:{version}:{case_set}:{role}"
        if any(r.get("id") == row_id for r in existing["rows"]):
            raise ValueError(
                "Scorecard row already exists; corrections require a new round ID"
            )
        rows.append(
            {
                "id": row_id,
                "date": day,
                "label": identifier(label or round_id),
                "code_revision": revision,
                "rule_engine": version,
                "model_id": next(iter(models)),
                "case_set": case_set,
                "role": role,
                "reviews": len(members),
                "failed_or_incomplete": len(members) - completed,
                "accuracy": {
                    "critical_high_caught": caught,
                    "critical_high_total": expected,
                    "critical_high_recall": ratio(caught, expected),
                    "all_severity_recall": ratio(all_caught, all_expected),
                    "findings": findings,
                    "false_claims": false,
                    "false_claims_per_review": ratio(false, completed),
                    "false_claim_share": ratio(false, findings),
                    "unsafe_fixes": unsafe,
                    "unsafe_fixes_per_review": ratio(unsafe, completed),
                },
                "cost_usd": cost,
                "model_seconds": distribution(
                    [(s.get("model") or {}).get("seconds") for s in members]
                ),
                "input_tokens": distribution(
                    [(s.get("model") or {}).get("input_tokens") for s in members]
                ),
                "end_to_end_seconds": distribution(
                    [s.get("end_to_end_seconds") for s in members]
                ),
                "p3b": p3b,
            }
        )
    return rows, registry


def append_scorecard(path: Path, report: dict, **options) -> list[dict]:
    """Append logical rows atomically; concurrent writers fail instead of losing data."""
    lock = path.with_name(path.name + ".lock")
    lock.open("x", encoding="utf-8").close()
    try:
        original = path.read_bytes()
        existing = json.loads(original)
        if existing.get("schema") != "archibrief-eval-scorecard/1" or not isinstance(
            existing.get("rows"), list
        ):
            raise ValueError("Unsupported scorecard schema")
        rows, registry = build_rows(report, existing, **options)
        updated = {
            **existing,
            "case_sets": registry,
            "rows": [*existing["rows"], *rows],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(updated, output, indent=2)
            output.write("\n")
        try:
            if path.read_bytes() != original:
                raise ValueError("Scorecard changed during append")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return rows
    finally:
        lock.unlink(missing_ok=True)
