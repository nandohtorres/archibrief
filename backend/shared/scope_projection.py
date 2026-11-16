"""Allowlisted public coverage; never expose parsed bodies or storage bindings."""

from collections import Counter

from backend.shared.review_scope import ADDRESS_PATTERN, validate_scope

GAP_LABELS = {
    "remote_source": "remote module not read",
    "source_unresolved": "module source unresolved",
    "source_missing": "module source missing",
    "source_outside_archive": "module source outside upload",
    "count_unresolved": "module count unresolved",
    "count_not_singleton": "module count not supported",
    "for_each_unsupported": "module for_each not supported",
    "cycle": "module cycle",
    "depth_limit": "module depth limit",
    "expansion_limit": "static expansion limit",
}
OTHER_LABELS = {
    "summary_cap": "outside the bounded AI summary",
    "summary_filtered": "resource type filtered from the AI summary",
    "not_retained": "resource body not retained",
    "model_not_invoked": "AI generation not invoked",
    "outcome_unknown": "AI delivery unconfirmed",
}


def public_review_scope(record: object) -> dict:
    if validate_scope(record) or record["status"] != "final" or record["state"] != "recorded":
        return {
            "version": "review-scope-public@1",
            "known_y": None,
            "x": None,
            "count_complete": False,
            "model_outcome": "unknown",
            "categories": None,
            "module_gaps": [],
            "gaps_complete": False,
            "warnings": [],
            "other_reasons": [],
        }
    return {
        "version": "review-scope-public@1",
        "known_y": record["known_y"],
        "x": record["x"],
        "count_complete": record["count_complete"],
        "model_outcome": record["model_outcome"],
        "categories": dict(record["categories"]),
        "other_reasons": [
            {"label": OTHER_LABELS[reason], "count": count}
            for reason, count in sorted(
                Counter(
                    d["reason"] for d in record["declarations"] if d["category"] == "other"
                ).items()
            )
        ],
        "module_gaps": [
            {
                "address": gap["address"]
                if ADDRESS_PATTERN.fullmatch(gap["address"])
                else "module (name unavailable)",
                "labels": [GAP_LABELS[reason] for reason in sorted(set(gap["reasons"]))],
            }
            for gap in record["module_gaps"]
        ],
        "gaps_complete": record["gaps_complete"],
        "warnings": ["Terraform JSON configuration not analyzed"] if record["warnings"] else [],
    }
