"""Build each demo's Stakeholder Brief sidecar (presentation version 2).

The saved demo reports stay unedited. This writes stakeholder/<id>.json
next to them with what the frontend's legacy reader needs: each finding's
assessment (severity, whether action is needed, who assessed it), its
concern and subject, and, for the model's findings, the plain summary
written by hand in scripts/demo_plain_language.json. The wording, pictures
and commitment tiers come from frontend/lib/stakeholder-brief.ts. No
prices, effort hours or loss figures are written (ADR-0062), and no model
is called.

Assessments are the same as the version 1 sidecars: rule findings use the
catalog severity of their concern (the demos were saved before findings
stored one, and their sidecars were checked by hand), and the model's
findings use the reviewer's severity.

    python scripts/build_demo_stakeholder.py            # rebuild all
    python scripts/build_demo_stakeholder.py --check    # fail if any differ
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.shared.assessment import CONFIGURATION_ASSESSMENTS
from backend.shared.models.finding import Finding, FindingType
from backend.shared.stakeholder.catalog import RECIPES, infer_concern
from backend.shared.stakeholder.presentation import brief_meta

DEMOS = ROOT / "frontend" / "public" / "demos"
PLAIN_LANGUAGE = ROOT / "scripts" / "demo_plain_language.json"
SIDECAR_VERSION = 2
# Must match PRESENTATION_VERSION in frontend/lib/stakeholder-brief.ts.
PRESENTATION = "stakeholder-brief@2026-11-15"
_AMOUNT = re.compile(
    r"(?:US\$|\$)\s?\d|\bUSD\s?\d|\d\s?(?:USD|dollars?)\b", re.IGNORECASE
)


def _rule_block(finding: Finding) -> dict | None:
    meta = brief_meta(finding)
    concern = (meta or {}).get("concern") or infer_concern(finding.finding)
    if concern in CONFIGURATION_ASSESSMENTS:
        severity = CONFIGURATION_ASSESSMENTS[concern]
    elif concern in RECIPES:
        severity = RECIPES[concern].severity
    else:
        return None
    return {
        "source": "rule",
        "concern": concern,
        "subject": (meta or {}).get("subject"),
        "severity": severity,
        "needs_action": True,
        "title": finding.finding,
        "what_could_happen": finding.risk_impact,
        "action": finding.recommendation,
    }


def _reviewer_block(text: dict) -> dict:
    return {
        "source": "reviewer",
        "concern": None,
        "subject": None,
        "severity": text["severity"],
        "needs_action": text["needs_action"],
        "title": text["title"],
        "what_could_happen": text["what_could_happen"],
        "action": text["action"],
    }


def build(demo_id: str, written: dict[str, dict]) -> str:
    report = json.loads(
        (DEMOS / "reports" / f"{demo_id}.json").read_text(encoding="utf-8")
    )
    blocks = {}
    for entry in report["findings"]:
        finding = Finding.model_validate(entry["record"])
        if finding.type == FindingType.DETERMINISTIC_RULE_RESULT:
            block = _rule_block(finding)
        elif finding.type == FindingType.NOT_OBSERVABLE:
            block = None
        else:
            text = written.get(finding.finding_id)
            if text is None:
                raise ValueError(
                    f"{demo_id}: no plain-language text for {finding.finding_id}"
                )
            block = _reviewer_block(text)
        if block is not None:
            blocks[finding.finding_id] = block
    for block in blocks.values():
        if block["source"] == "reviewer":
            for field in ("title", "what_could_happen", "action"):
                if _AMOUNT.search(block[field]):
                    raise ValueError(
                        f"{demo_id}: a dollar amount in reviewer text ({field})"
                    )
    view = {
        "version": SIDECAR_VERSION,
        "presentation": PRESENTATION,
        "review_id": report["review_id"],
        "blocks": blocks,
    }
    return json.dumps(view, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if a view is out of date"
    )
    args = parser.parse_args()

    index = json.loads((DEMOS / "demos.json").read_text(encoding="utf-8"))
    written = json.loads(PLAIN_LANGUAGE.read_text(encoding="utf-8"))
    out_dir = DEMOS / "stakeholder"
    out_dir.mkdir(exist_ok=True)
    stale = []
    for entry in index["demos"]:
        demo_id = entry["id"]
        text = build(demo_id, written.get(demo_id, {}))
        target = out_dir / f"{demo_id}.json"
        if args.check:
            # Compared without line endings: a Windows checkout may hold CRLF.
            if (
                not target.exists()
                or target.read_text(encoding="utf-8").splitlines() != text.splitlines()
            ):
                stale.append(demo_id)
            continue
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"{demo_id}: {len(json.loads(text)['blocks'])} findings")
    if stale:
        print("out of date:", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
