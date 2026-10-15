"""Builds the deployment zip for each Lambda listed in LAMBDA_SPECS.

Found missing 2026-10-12 (see Work-Project-Issues-Log.md): six Lambdas
built across recent sessions — create_upload, clarify_review,
deeper_review, get_demo, get_review, store_clarification_token — had no
build/*.zip at all, which `terraform apply` needs to exist at plan time
(aws_lambda_function's `filename` must point at a real file). No
packaging script existed anywhere in this repo to produce one; the
earlier Lambdas' zips (admin_authorizer, finalize, ingest, etc.) were
apparently built some other, non-reproducible way, and turned out to be
a kitchen-sink bundle (finalize's old zip carried a full hcl2 install it
never imports) rather than scoped per-Lambda deps — this script fixes
that too, bundling only each Lambda's actual (transitive) imports.

Also found while building this (2026-10-12): `finalize` and `ingest`'s
*existing* zips were stale — both handlers (and backend/shared/clients,
which several Lambdas depend on) genuinely changed across this and
earlier sessions (`git status` confirms real diffs, not just a touched
mtime) after their last zip was built back on 2026-09-08. Deploying the
old zips would have silently run outdated code — the
cost_estimate_tier/DynamoDB-merge fix (finalize) and the S3-archive-
download path (ingest) would never have actually taken effect. Added
both here so `python scripts/package_lambdas.py` (no args) rebuilds
every Lambda whose source could plausibly have drifted from its zip,
not just the ones that never had one.

Run from the repo root:  python scripts/package_lambdas.py [name ...]
With no arguments, packages every Lambda in LAMBDA_SPECS.

Third-party dependencies are downloaded as manylinux/cp312 wheels via
`pip install --platform ... --only-binary=:all: --target`, NOT installed
normally — this machine's Python is 3.14 on Windows, but the deployed
Lambda runtime is python3.12 on Linux x86_64 (see
infra/modules/step-functions-lambda/main.tf's `runtime = "python3.12"`,
no `architectures` override, so the default x86_64 applies). pip
supports downloading wheels for a different target platform without
executing any of that platform's code, which is what makes this safe to
run from here at all. boto3/botocore are never bundled — the Lambda
runtime provides them natively, matching every existing zip in this
repo (confirmed by inspecting admin_authorizer's/finalize's zips
directly, not assumed).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

# Each entry: Lambda name -> (source files/dirs to copy verbatim,
# relative to ROOT; third-party PyPI packages to bundle as Linux wheels).
# Dependency lists were derived by reading each handler's actual imports
# (transitively — e.g. deeper_review imports validate.handler, which
# imports pydantic), not guessed from the Lambda's name.
LAMBDA_SPECS: dict[str, dict[str, list[str]]] = {
    "create_upload": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/create_upload/__init__.py",
            "backend/lambdas/create_upload/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
        ],
        "packages": [],
    },
    "clarify_review": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/clarify_review/__init__.py",
            "backend/lambdas/clarify_review/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/kill_switch.py",
        ],
        "packages": [],
    },
    "mark_review_failed": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/mark_review_failed/__init__.py",
            "backend/lambdas/mark_review_failed/handler.py",
        ],
        "packages": [],
    },
    "store_clarification_token": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/store_clarification_token/__init__.py",
            "backend/lambdas/store_clarification_token/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
        ],
        "packages": [],
    },
    "get_demo": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/get_demo/__init__.py",
            "backend/lambdas/get_demo/handler.py",
            "backend/lambdas/get_demo/reference_report.json",
        ],
        "packages": [],
    },
    "get_review": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/get_review/__init__.py",
            "backend/lambdas/get_review/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/report.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
        ],
        # report.py -> backend.shared.models.finding -> pydantic.
        "packages": ["pydantic>=2.0"],
    },
    "rule_engine": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/rule_engine/__init__.py",
            "backend/lambdas/rule_engine/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
        ],
        # backend.shared.models.finding -> pydantic.
        "packages": ["pydantic>=2.0"],
    },
    "audit": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/audit/__init__.py",
            "backend/lambdas/audit/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
        ],
        "packages": [],
    },
    "finalize": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/finalize/__init__.py",
            "backend/lambdas/finalize/handler.py",
            "backend/agent/__init__.py",
            "backend/agent/nodes/__init__.py",
            "backend/agent/nodes/preflight.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
        ],
        # backend.shared.models.finding -> pydantic.
        "packages": ["pydantic>=2.0"],
    },
    "ingest": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/ingest/__init__.py",
            "backend/lambdas/ingest/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
        ],
        # Static HCL parsing (ADR-0027) — never a terraform binary.
        "packages": ["python-hcl2>=6.0"],
    },
    "deeper_review": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/deeper_review/__init__.py",
            "backend/lambdas/deeper_review/handler.py",
            "backend/lambdas/validate/__init__.py",
            "backend/lambdas/validate/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/kill_switch.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            # compute_presentation for the {record, presentation} response.
            "backend/shared/report.py",
        ],
        # validate.handler imports pydantic directly for ValidationError.
        "packages": ["pydantic>=2.0"],
    },
    # admin_authorizer and validate were deployed from zips built outside
    # this script (Codex F23); listed here so every Lambda builds the same
    # way. tests/backend/test_package_lambdas.py keeps these lists honest.
    "admin_authorizer": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/admin_authorizer/__init__.py",
            "backend/lambdas/admin_authorizer/handler.py",
        ],
        # Standard library only (hmac, os).
        "packages": [],
    },
    "validate": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/validate/__init__.py",
            "backend/lambdas/validate/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
        ],
        # Imports pydantic directly for ValidationError.
        "packages": ["pydantic>=2.0"],
    },
}

_PIP_PLATFORM_ARGS = [
    "--platform",
    "manylinux2014_x86_64",
    "--implementation",
    "cp",
    "--python-version",
    "3.12",
    "--abi",
    "cp312",
    "--only-binary=:all:",
]


def _stage_sources(name: str, sources: list[str], staging_dir: Path) -> None:
    for rel_path in sources:
        src = ROOT / rel_path
        if not src.exists():
            raise FileNotFoundError(f"{name}: expected source file missing: {rel_path}")
        dest = staging_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _install_packages(packages: list[str], staging_dir: Path) -> None:
    if not packages:
        return
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            *_PIP_PLATFORM_ARGS,
            "--target",
            str(staging_dir),
            *packages,
        ],
        check=True,
    )
    # pip's downloaded dist-info/__pycache__ directories aren't needed at
    # runtime and only bloat the zip — strip them, same as every existing
    # zip in this repo (confirmed: admin_authorizer's/finalize's zips
    # carry no __pycache__ entries).
    for junk_dir in staging_dir.rglob("__pycache__"):
        shutil.rmtree(junk_dir, ignore_errors=True)


def _zip_staging_dir(staging_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(staging_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(staging_dir))


def package(name: str) -> Path:
    spec = LAMBDA_SPECS[name]
    staging_dir = BACKEND / "lambdas" / name / "build" / "_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    try:
        _stage_sources(name, spec["sources"], staging_dir)
        _install_packages(spec["packages"], staging_dir)
        zip_path = BACKEND / "lambdas" / name / "build" / f"{name}.zip"
        _zip_staging_dir(staging_dir, zip_path)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return zip_path


def main() -> None:
    requested = sys.argv[1:] or list(LAMBDA_SPECS)
    unknown = [n for n in requested if n not in LAMBDA_SPECS]
    if unknown:
        raise SystemExit(
            f"Unknown Lambda name(s): {unknown}. Known: {list(LAMBDA_SPECS)}"
        )

    for name in requested:
        zip_path = package(name)
        size_kb = zip_path.stat().st_size / 1024
        print(f"{name}: {zip_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
