"""Build the stakeholder view (plain terms, costs, budget) for each demo.

The saved demo reports stay unedited. This writes stakeholder/<id>.json
next to them, built by the same code a live report uses
(backend/shared/stakeholder/brief.py): rule findings from the catalog,
the model's findings from the hand-written text in
scripts/demo_plain_language.json, and prices from the price table. The
Terraform's resource summary comes from the demo's archive, so fixes
are priced at the sizes the code really uses. No model is called.

    python scripts/build_demo_stakeholder.py            # rebuild all
    python scripts/build_demo_stakeholder.py --check    # fail if any differ
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.shared.models.finding import Finding, FindingType, PlainLanguage
from backend.shared.stakeholder.brief import build_stakeholder_view
from scripts.build_demo_architectures import DEMOS, _extract_tf

PLAIN_LANGUAGE = ROOT / "scripts" / "demo_plain_language.json"


def build(demo_id: str, written: dict[str, dict]) -> str:
    report = json.loads((DEMOS / "reports" / f"{demo_id}.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as scratch:
        parsed = parse_terraform_files(_extract_tf(DEMOS / f"{demo_id}.tar", Path(scratch)))
    findings = []
    for entry in report["findings"]:
        finding = Finding.model_validate(entry["record"])
        text = written.get(finding.finding_id)
        if finding.type != FindingType.DETERMINISTIC_RULE_RESULT:
            if text is None:
                raise ValueError(f"{demo_id}: no plain-language text for {finding.finding_id}")
            plain = PlainLanguage(written_by="reviewer", **text)
            finding = finding.model_copy(update={"plain": plain})
        findings.append(finding)
    view = build_stakeholder_view(
        findings, build_resource_summary(vars(parsed)), report["baseline_answers"]
    )
    view["review_id"] = report["review_id"]
    return json.dumps(view, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a view is out of date")
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
        budget = json.loads(text)["budget"]
        print(
            f"{demo_id}: {budget['item_count']} items, {budget['free_count']} free, "
            f"${budget['monthly_known']}/month known, {budget['effort_label']}"
        )
    if stale:
        print("out of date:", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
