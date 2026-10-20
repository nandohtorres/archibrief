"""Build the architecture graph for each demo in frontend/public/demos/.

The graph comes from the demo's archive and its saved review, through the
same builder a live review uses (backend/lambdas/rule_engine/
architecture.py), and is written to architecture/<id>.json next to the
report. No model is called.

    python scripts/build_demo_architectures.py            # rebuild all
    python scripts/build_demo_architectures.py --check    # fail if any differ
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.architecture import build_architecture

DEMOS = ROOT / "frontend" / "public" / "demos"


def _extract_tf(archive: Path, into: Path) -> list[str]:
    """Write the archive's .tf files under `into`; return their paths."""
    paths = []
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if not member.isfile() or name.suffix != ".tf":
                continue
            if name.is_absolute() or ".." in name.parts:
                raise ValueError(f"{archive.name}: unsafe path {member.name}")
            target = into.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            paths.append(str(target))
    return sorted(paths)


def build(demo_id: str) -> str:
    report = json.loads(
        (DEMOS / "reports" / f"{demo_id}.json").read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory() as scratch:
        parsed = parse_terraform_files(
            _extract_tf(DEMOS / f"{demo_id}.tar", Path(scratch))
        )
    findings = [entry.get("record", entry) for entry in report["findings"]]
    graph = build_architecture(vars(parsed), findings)
    graph["review_id"] = report["review_id"]
    return json.dumps(graph, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if a graph is out of date"
    )
    args = parser.parse_args()

    index = json.loads((DEMOS / "demos.json").read_text(encoding="utf-8"))
    out_dir = DEMOS / "architecture"
    out_dir.mkdir(exist_ok=True)
    stale = []
    for entry in index["demos"]:
        demo_id = entry["id"]
        text = build(demo_id)
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
        graph = json.loads(text)
        print(
            f"{demo_id}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges, "
            f"{len(graph['account_findings'])} account-wide findings"
        )
    if stale:
        print("out of date:", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
