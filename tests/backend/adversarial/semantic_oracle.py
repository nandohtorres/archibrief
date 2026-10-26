"""Versioned review criteria, separate from frozen deterministic verdicts.

No keyword matcher can establish these claims' semantic correctness. Consumers
must keep semantic adjudication unscored until an actual review is recorded.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_semantic_oracle() -> dict:
    return json.loads(
        Path(__file__).with_name("semantic_oracle.json").read_text(encoding="utf-8")
    )


def semantic_review(case_id: str, oracle: dict) -> dict:
    criteria = [case for case in oracle["cases"] if case["case"] == case_id]
    return {
        "oracle_version": oracle["version"],
        "criteria": [case["id"] for case in criteria],
        "status": "not_scored" if criteria else "outside_supplemental_scope",
    }
