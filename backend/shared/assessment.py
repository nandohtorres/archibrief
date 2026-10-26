"""Versioned risk/action assessment, independent of evidence type and confidence.

Reuses the existing curated rule catalog and structured plain-language output.
Missing assessments stay unknown; free text is never interpreted as a score.
This module deliberately has no model/SDK dependencies so chat can reuse it.
"""

from __future__ import annotations

from typing import Any

from backend.shared.stakeholder.catalog import RECIPES, SEVERITIES

CONFIGURATION_ASSESSMENTS = {
    "placement_single_az": "high",
    "invalid_sqs_mapping": "high",
    "versioned_retention_gap": "medium",
}


def finding_assessment(finding: dict[str, Any]) -> dict[str, Any]:
    unknown = {
        "version": 1,
        "severity": None,
        "action": "unknown",
        "source": "unassessed",
    }
    if finding.get("type") == "not-observable":
        return unknown
    if finding.get("type") == "deterministic-rule-result":
        # Only explicit rule keys count. Text matching a catalog title is
        # insufficient provenance for assigning a risk assessment.
        concern = finding.get("concern")
        recipe = RECIPES.get(concern) if isinstance(concern, str) else None
        if isinstance(concern, str) and concern in CONFIGURATION_ASSESSMENTS:
            return {
                "version": 1,
                "severity": CONFIGURATION_ASSESSMENTS[concern],
                "action": "needed",
                "source": "rule",
            }
        if recipe is not None:
            return {
                "version": 1,
                "severity": recipe.severity,
                "action": "needed",
                "source": "rule",
            }
        return unknown
    plain = finding.get("plain")
    if (
        isinstance(plain, dict)
        and plain.get("written_by") in ("model", "reviewer")
        and plain.get("severity") in SEVERITIES
        and type(plain.get("needs_action")) is bool
    ):
        return {
            "version": 1,
            # A no-action assessment has no risk to rank. Preserve the
            # original plain-language record separately for inspection.
            "severity": plain["severity"] if plain["needs_action"] else None,
            "action": "needed" if plain["needs_action"] else "none",
            "source": plain["written_by"],
        }
    return unknown


def assessment_rank(finding: dict[str, Any]) -> tuple[int, int]:
    assessment = finding_assessment(finding)
    return (
        {"needed": 0, "unknown": 1, "none": 2}[assessment["action"]],
        SEVERITIES.index(assessment["severity"]) if assessment["severity"] else len(SEVERITIES),
    )
