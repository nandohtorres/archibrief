"""Build the deployment ZIP for each Lambda listed in LAMBDA_SPECS.

`terraform plan` needs every Lambda's build/*.zip to exist, since
aws_lambda_function's `filename` must point at a real file. Each zip
bundles only that Lambda's own (transitive) imports, never a shared
kitchen-sink bundle, and rebuilding every Lambda from source keeps a zip
from silently running code older than its handler.

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
run from here at all. boto3/botocore are bundled only into ask_question
(see its spec); every other Lambda uses the runtime's own copy, matching
the deployed zips.

Reproducible builds: third-party versions are pinned in
scripts/lambda_constraints.txt, and the zip is written with fixed
timestamps and permissions in a fixed order. Rebuilding unchanged code
gives a byte-identical zip, so `terraform plan` only shows Lambdas whose
code or dependencies really changed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
CONSTRAINTS = ROOT / "scripts" / "lambda_constraints.txt"

# Fixed metadata for every zip entry, so the same files always give the
# same bytes (zip format can't store dates before 1980).
_ZIP_DATE_TIME = (2026, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = (0o100644 & 0xFFFF) << 16  # regular file, rw-r--r--

# Each entry: Lambda name -> (source files/dirs to copy verbatim,
# relative to ROOT; third-party PyPI packages to bundle as Linux wheels).
# Dependency lists were derived by reading each handler's actual imports
# (transitively — e.g. deeper_review imports validate.handler, which
# imports pydantic), not guessed from the Lambda's name.
LAMBDA_SPECS: dict[str, dict[str, list[str]]] = {
    "review_worker": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/review_worker/__init__.py",
            "backend/lambdas/review_worker/handler.py",
            "backend/shared/analysis_quality.py",
            "backend/shared/architecture_links.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/admission.py",
            "backend/shared/retention.py",
            "backend/shared/kill_switch.py",
        ],
        "packages": ["boto3"],
    },
    "submit_review": {
        "sources": [
            "backend/shared/http.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/submit_review/__init__.py",
            "backend/lambdas/submit_review/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/admission.py",
            "backend/shared/public_access.py",
            "backend/shared/retention.py",
            "backend/shared/kill_switch.py",
        ],
        "packages": ["boto3"],
    },
    "create_upload": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/uploads.py",
            "backend/shared/retention.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/create_upload/__init__.py",
            "backend/lambdas/create_upload/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/http.py",
        ],
        "packages": ["boto3"],
    },
    "clarify_review": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/clarify_review/__init__.py",
            "backend/lambdas/clarify_review/handler.py",
            "backend/shared/retention.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/kill_switch.py",
            "backend/shared/http.py",
        ],
        "packages": ["boto3"],
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
            "backend/shared/__init__.py",
            "backend/shared/http.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/get_demo/__init__.py",
            "backend/lambdas/get_demo/handler.py",
            "backend/lambdas/get_demo/reference_report.json",
            "backend/shared/__init__.py",
            "backend/shared/http.py",
        ],
        "packages": [],
    },
    "get_review": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/get_review/__init__.py",
            "backend/lambdas/get_review/handler.py",
            "backend/shared/deeper_jobs.py",
            "backend/shared/review_projection.py",
            "backend/shared/architecture_links.py",
            "backend/shared/analysis_quality.py",
            "backend/shared/assessment.py",
            "backend/shared/retention.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/report.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/brief.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/stakeholder/pricing.py",
            "backend/shared/http.py",
        ],
        # report.py -> backend.shared.models.finding -> pydantic.
        "packages": ["pydantic>=2.0"],
    },
    "rule_engine": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/rule_engine/__init__.py",
            "backend/lambdas/rule_engine/architecture.py",
            "backend/lambdas/rule_engine/handler.py",
            "backend/lambdas/rule_engine/hcl_eval.py",
            "backend/shared/hcl_eval.py",
            "backend/lambdas/rule_engine/resource_summary.py",
            "backend/shared/terraform_observations.py",
            "backend/shared/configuration_checks.py",
            "backend/shared/__init__.py",
            "backend/shared/architecture_links.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/stakeholder/pricing.py",
            "backend/shared/terraform_scope.py",
            "backend/shared/trivy_checks.py",
        ],
        # backend.shared.models.finding -> pydantic; hcl_eval decodes
        # jsonencode() expressions with python-hcl2 (ADR-0048).
        "packages": ["pydantic>=2.0", "python-hcl2>=6.0"],
    },
    # Runs the Trivy binary from the trivy layer (scripts/build_trivy_layer.py,
    # ADR-0048). Structural module-source neutralization uses python-hcl2;
    # its version is pinned by lambda_constraints.txt.
    "scan": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/scan/__init__.py",
            "backend/lambdas/scan/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/archive.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/terraform_scope.py",
            "backend/shared/trivy_checks.py",
        ],
        "packages": ["python-hcl2>=6.0"],
    },
    "audit": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/audit/__init__.py",
            "backend/lambdas/audit/handler.py",
            "backend/shared/retention.py",
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
            "backend/shared/analysis_quality.py",
            "backend/shared/retention.py",
            "backend/agent/__init__.py",
            "backend/agent/nodes/__init__.py",
            "backend/agent/nodes/preflight.py",
            "backend/shared/__init__.py",
            "backend/shared/architecture_links.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/stakeholder/pricing.py",
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
            "backend/shared/hcl_eval.py",
            "backend/shared/__init__.py",
            "backend/shared/archive.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/terraform_scope.py",
        ],
        # Static HCL parsing (ADR-0027) — never a terraform binary.
        "packages": ["python-hcl2>=6.0"],
    },
    "deeper_review": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/deeper_review/__init__.py",
            "backend/lambdas/deeper_review/handler.py",
            "backend/lambdas/deeper_review/worker.py",
            "backend/shared/deeper_jobs.py",
            "backend/shared/analysis_quality.py",
            "backend/shared/assessment.py",
            "backend/shared/retention.py",
            "backend/lambdas/validate/__init__.py",
            "backend/lambdas/validate/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/kill_switch.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/brief.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/stakeholder/pricing.py",
            # compute_presentation for the {record, presentation} response.
            "backend/shared/report.py",
            "backend/shared/http.py",
        ],
        # Both HTTP admission and the background worker use this package.
        "packages": ["pydantic>=2.0", "boto3"],
    },
    # The report chat (ADR-0050). ask_question makes the one paid model
    # call; it reuses retrieve.vector_search, which needs only the shared
    # clients. The shared report projection validates stored children with
    # the same pydantic model as the report API. boto3 is bundled here (the same pin as
    # the AgentCore runtime lock) because it calls S3 Vectors, and AWS no
    # longer publishes which boto3 the python3.12 runtime carries in each
    # Region: an older one wouldn't know the s3vectors client.
    "ask_question": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/agent/__init__.py",
            "backend/agent/nodes/__init__.py",
            "backend/agent/nodes/retrieve.py",
            "backend/chat/__init__.py",
            "backend/chat/access.py",
            "backend/chat/answer.py",
            "backend/chat/context.py",
            "backend/chat/observe.py",
            "backend/chat/pricing.py",
            "backend/chat/prompt.py",
            "backend/chat/suggested.py",
            "backend/chat/verify.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/ask_question/__init__.py",
            "backend/lambdas/ask_question/handler.py",
            "backend/shared/deeper_jobs.py",
            "backend/shared/review_projection.py",
            "backend/shared/architecture_links.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/pricing.py",
            "backend/shared/analysis_quality.py",
            "backend/shared/assessment.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/retention.py",
            "backend/shared/__init__.py",
            "backend/shared/citations.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/kill_switch.py",
            "backend/shared/sanitize.py",
            "backend/shared/http.py",
        ],
        "packages": ["boto3", "pydantic>=2.0"],
    },
    # Read-only transcript; no model code bundled.
    "list_questions": {
        "sources": [
            "backend/shared/http.py",
            "backend/shared/public_access.py",
            "backend/shared/admission.py",
            "backend/__init__.py",
            "backend/chat/__init__.py",
            "backend/chat/access.py",
            "backend/chat/context.py",
            "backend/chat/suggested.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/list_questions/__init__.py",
            "backend/lambdas/list_questions/handler.py",
            "backend/shared/deeper_jobs.py",
            "backend/shared/review_projection.py",
            "backend/shared/architecture_links.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/pricing.py",
            "backend/shared/analysis_quality.py",
            "backend/shared/assessment.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/retention.py",
            "backend/shared/__init__.py",
            "backend/shared/clients/__init__.py",
            "backend/shared/sanitize.py",
            "backend/shared/http.py",
        ],
        "packages": ["pydantic>=2.0"],
    },
    "spend_stop": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/spend_stop/__init__.py",
            "backend/lambdas/spend_stop/handler.py",
        ],
        "packages": [],
    },
    # validate is listed too, so every Lambda builds the same way.
    # tests/backend/test_package_lambdas.py keeps these lists honest.
    "validate": {
        "sources": [
            "backend/__init__.py",
            "backend/lambdas/__init__.py",
            "backend/lambdas/validate/__init__.py",
            "backend/lambdas/validate/handler.py",
            "backend/shared/__init__.py",
            "backend/shared/models/__init__.py",
            "backend/shared/models/finding.py",
            "backend/shared/stakeholder/__init__.py",
            "backend/shared/stakeholder/catalog.py",
            "backend/shared/stakeholder/pricing.py",
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
            "--constraint",
            str(CONSTRAINTS),
            "--target",
            str(staging_dir),
            *packages,
        ],
        check=True,
    )
    check_all_pinned(staging_dir)
    # pip's downloaded dist-info/__pycache__ directories aren't needed at
    # runtime and only bloat the zip — strip them, same as every existing
    # zip in this repo (confirmed: finalize's zip
    # carry no __pycache__ entries).
    for junk_dir in staging_dir.rglob("__pycache__"):
        shutil.rmtree(junk_dir, ignore_errors=True)
    # pip on Windows writes .exe launchers for console scripts (python-hcl2's
    # hcl2tojson etc.) into bin/. Lambda runs Linux and never calls them, and
    # they come out different on every build, as does the RECORD file
    # listing their hashes. Neither is needed to import the packages.
    shutil.rmtree(staging_dir / "bin", ignore_errors=True)
    for record in staging_dir.glob("*.dist-info/RECORD"):
        record.unlink()


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_versions(constraints: Path = CONSTRAINTS) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in constraints.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        if not sep:
            raise ValueError(f"{constraints.name}: not an exact pin: {line!r}")
        pins[_normalize(name)] = version.strip()
    return pins


def check_all_pinned(staging_dir: Path, constraints: Path = CONSTRAINTS) -> None:
    """Fail if pip bundled a package, or a version, that isn't pinned."""
    pins = pinned_versions(constraints)
    for dist_info in staging_dir.glob("*.dist-info"):
        name, _, version = dist_info.name[: -len(".dist-info")].rpartition("-")
        if pins.get(_normalize(name)) != version:
            raise SystemExit(
                f"{name} {version} was bundled but isn't pinned in "
                f"{constraints.name}. Add it there on purpose, then rebuild."
            )


def _zip_staging_dir(staging_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    files = sorted(
        (p for p in staging_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(staging_dir).as_posix(),
    )
    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_path in files:
            info = zipfile.ZipInfo(
                file_path.relative_to(staging_dir).as_posix(), _ZIP_DATE_TIME
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = _ZIP_FILE_MODE
            zf.writestr(info, file_path.read_bytes())


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
