"""Rebuild the demo archives in frontend/public/demos/ from pinned commits.

Each demo reviews real, public Terraform (docs/demos.md). This fetches
only the listed directories at the pinned commit, packs their .tf files
unchanged, and adds SOURCE.md plus the project's license file. Output is
byte-for-byte reproducible (fixed timestamps and owners), so a rebuilt
archive can be compared with the committed one.

    python scripts/build_demo_archives.py            # rebuild all
    python scripts/build_demo_archives.py --check    # fail if any differ

Needs git and network access; nothing else is downloaded or run.
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "demos"

DEMOS = {
    "breach-pattern": {
        "repo": "https://github.com/RhinoSecurityLabs/cloudgoat",
        "name": "cloudgoat",
        "commit": "63c65bd26edc6919499adfa20b176c450e35c33c",
        "dirs": ["cloudgoat/scenarios/aws/cloud_breach_s3/terraform"],
        "license_file": "LICENSE",
        "license": "BSD-3-Clause",
        "about": "Rhino Security Labs' CloudGoat scenario cloud_breach_s3: a deliberately "
        "vulnerable-by-design AWS lab. Its attack path matches the one publicly reported "
        "for the 2019 Capital One breach. It is not Capital One's code.",
    },
    "medicare-platform": {
        "repo": "https://github.com/CMSgov/cdap",
        "name": "cdap",
        "commit": "e3b284998d05d77660f6a734a11aa2b42de1f205",
        "dirs": [
            "terraform/services/020-vpc-network",
            "terraform/services/security-groups",
            "terraform/services/api-waf",
            "terraform/services/kms-keys",
            "terraform/services/backup-plan",
            "terraform/services/bucket-access-logs",
            "terraform/modules/vpc",
            "terraform/modules/firewall",
            "terraform/modules/platform",
        ],
        "license_file": "LICENSE",
        "license": "CC0-1.0",
        "about": "The Centers for Medicare & Medicaid Services (CMS) platform for the AB2D, "
        "BCDA and DPC Medicare data APIs: the network, firewall, encryption-key, backup and "
        "access-log slice.",
    },
    "fec-database": {
        "repo": "https://github.com/fecgov/fec-infrastructure",
        "name": "fec-infrastructure",
        "commit": "bd6fbd5ca00e3927b0d2ce0fd543ec9395315edd",
        "dirs": ["terraform"],
        "license_file": "LICENSE.md",
        "license": "US Government work (public domain in the US); see LICENSE.md",
        "about": "The Federal Election Commission's custom AWS infrastructure: its Aurora "
        "database clusters and their network (last changed in 2020).",
    },
}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def fetch(demo: dict, into: Path) -> Path:
    """Sparse, shallow checkout of just the demo's directories at its commit."""
    repo = into / demo["name"]
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("remote", "add", "origin", demo["repo"], cwd=repo)
    _git(
        "sparse-checkout",
        "set",
        "--no-cone",
        "/" + demo["license_file"],
        *(f"/{d}/" for d in demo["dirs"]),
        cwd=repo,
    )
    _git("fetch", "-q", "--depth", "1", "origin", demo["commit"], cwd=repo)
    _git("checkout", "-q", "FETCH_HEAD", cwd=repo)
    return repo


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def build(demo_id: str, demo: dict, repo: Path) -> bytes:
    buffer = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for directory in demo["dirs"]:
            for path in sorted((repo / directory).rglob("*.tf")):
                _add(tar, path.relative_to(repo).as_posix(), path.read_bytes())
                count += 1
        source = (
            f"# Source\n\n{demo['about']}\n\n- Repository: {demo['repo']}\n"
            f"- Commit: {demo['commit']}\n- License: {demo['license']}\n"
            f"- Files: the .tf files under {', '.join(demo['dirs'])}, unchanged.\n"
        )
        _add(tar, "SOURCE.md", source.encode("utf-8"))
        _add(tar, f"LICENSE-{demo['name']}", (repo / demo["license_file"]).read_bytes())
    if not count:
        raise SystemExit(f"{demo_id}: no .tf files found")
    print(f"{demo_id}: {count} .tf files")
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare, don't write")
    args = parser.parse_args()
    differs = []
    with tempfile.TemporaryDirectory() as tmp:
        for demo_id, demo in DEMOS.items():
            data = build(demo_id, demo, fetch(demo, Path(tmp)))
            target = OUT / f"{demo_id}.tar"
            if args.check:
                if not target.exists() or target.read_bytes() != data:
                    differs.append(demo_id)
            else:
                target.write_bytes(data)
    if differs:
        print("differs from the committed archive:", ", ".join(differs))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
