"""Offline demo comparison; uses the deployed scanner's isolation policy.

Run from the repo root with the existing backend Python environment.
Keeps extracted scratch inputs under ignored backend/build/; deletes no files.
"""

import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

from backend.lambdas.scan.handler import neutralize_remote_sources, run_trivy
from backend.shared.trivy_checks import TRUSTED_CHECK_IDS

root = Path(__file__).resolve().parents[2]
archives = root / "frontend/public/demos"
output = root / "docs/evidence/trivy"
output.mkdir(parents=True, exist_ok=True)
scratch = root / "backend/build"
scratch.mkdir(parents=True, exist_ok=True)
trivy = shutil.which("trivy")
if not trivy:
    raise SystemExit("Local Trivy executable is required; no download attempted")
version = subprocess.run([trivy, "--version"], capture_output=True, text=True, check=True)
summary = {"trivy_version": version.stdout.strip(), "demos": {}}
for archive in sorted(archives.glob("*.tar")):
    scan_dir = Path(tempfile.mkdtemp(prefix=f"comparison-{archive.stem}-", dir=scratch))
    with tarfile.open(archive) as tar:
        tar.extractall(scan_dir, filter="data")
    files = sorted(str(p) for p in scan_dir.rglob("*.tf"))
    changed = neutralize_remote_sources(files, str(scan_dir))
    report = run_trivy(str(scan_dir), trivy)
    (output / f"{archive.stem}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    failures = [
        finding
        for result in report.get("Results", [])
        for finding in result.get("Misconfigurations", [])
        if finding.get("Status") == "FAIL"
    ]
    saved = archives / "reports" / f"{archive.stem}.json"
    records = (
        [f["record"] for f in json.loads(saved.read_text())["findings"]]
        if saved.exists()
        else None
    )
    summary["demos"][archive.stem] = {
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "terraform_files": len(files),
        "remote_sources_neutralized": changed,
        "trivy_failures": len(failures),
        "severity": dict(sorted(Counter(f["Severity"] for f in failures).items())),
        "check_ids": dict(sorted(Counter(f["ID"] for f in failures).items())),
        "trusted_check_failures": sum(f["ID"] in TRUSTED_CHECK_IDS for f in failures),
        "saved_report": str(saved.relative_to(root)).replace("\\", "/") if records is not None else None,
        "saved_finding_types": dict(sorted(Counter(f["type"] for f in records).items())) if records is not None else None,
    }
(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
