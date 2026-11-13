"""Contract-shaped test data; no dependency on the P0 implementation."""

from copy import deepcopy
from importlib import import_module


def scope_api():
    # Import during the test, so the absent module cannot prevent collection
    # of ingest, handoff and ledger tests on the pre-P0 baseline.
    return import_module("backend.shared.review_scope")


def declaration(
    kind="aws_s3_bucket", key="main", *, address=None, instances=1, retained=True
):
    return {
        "address": address or f"{kind}.{key}",
        "type": kind,
        "parsed_key": key,
        "instances": instances,
        "retained": retained,
        "in_summary": None,
        "sent": None,
        "category": None,
        "reason": None,
    }


def pending_scope(declarations=(), *, state="recorded", gaps=()):
    return {
        "version": "review_scope@1",
        "status": "pending",
        "state": state,
        "known_y": len(declarations) if state == "recorded" else None,
        "count_complete": True,
        "model_outcome": None,
        "x": None,
        "sent_count": None,
        # Owner answer to Q1: pending counts are null, not zero.
        "categories": {"reviewed": None, "zero_copy": None, "unsupported": None, "other": None},
        "declarations": deepcopy(list(declarations)),
        "module_gaps": deepcopy(list(gaps)),
        "gaps_complete": True,
        "warnings": [],
    }


def completed_scope():
    """One independently specified, fully serialized-record-compatible answer."""
    return {
        "version": "review_scope@1",
        "status": "final",
        "state": "recorded",
        "known_y": 1,
        "count_complete": True,
        "model_outcome": "completed",
        "x": 1,
        "sent_count": 1,
        "categories": {"reviewed": 1, "zero_copy": 0, "unsupported": 0, "other": 0},
        "declarations": [
            {
                "address": "aws_s3_bucket.main",
                "type": "aws_s3_bucket",
                "parsed_key": "main",
                "instances": 1,
                "retained": True,
                "in_summary": True,
                "sent": True,
                "category": "reviewed",
                "reason": None,
            }
        ],
        "module_gaps": [],
        "gaps_complete": True,
        "warnings": [],
    }
