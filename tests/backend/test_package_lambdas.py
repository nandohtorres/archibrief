"""Packaging regression tests.

scripts/package_lambdas.py lists each Lambda's source files by hand. A
handler that gains a `backend.*` import without the spec being updated
deploys fine and then fails at cold start with ModuleNotFoundError.
These tests walk each
handler's imports transitively and require every reached module — and
every package __init__ on the way — to be in that Lambda's sources.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_package_script():
    spec = importlib.util.spec_from_file_location(
        "package_lambdas", ROOT / "scripts" / "package_lambdas.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PACKAGER = _load_package_script()
LAMBDA_SPECS = PACKAGER.LAMBDA_SPECS


def test_scan_package_includes_structural_hcl_parser_dependency():
    assert any(package.startswith("python-hcl2") for package in LAMBDA_SPECS["scan"]["packages"])


def _module_file(module: str) -> Path | None:
    base = ROOT / Path(*module.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    return None


def _backend_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("backend"))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and (node.module or "").startswith("backend")
        ):
            found.add(node.module)
            # `from backend.x import y` may name a submodule y.
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return {m for m in found if _module_file(m) is not None}


def _required_sources(handler_module: str) -> set[str]:
    required: set[str] = set()
    pending = [handler_module]
    seen: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        # Every parent package's __init__.py must ship too.
        parts = module.split(".")
        for i in range(1, len(parts)):
            init = _module_file(".".join(parts[:i]))
            if init is not None:
                required.add(init.relative_to(ROOT).as_posix())
        path = _module_file(module)
        required.add(path.relative_to(ROOT).as_posix())
        pending.extend(_backend_imports(path))
    return required


@pytest.mark.parametrize("name", sorted(LAMBDA_SPECS))
def test_every_transitive_backend_import_is_packaged(name):
    required = _required_sources(f"backend.lambdas.{name}.handler")
    missing = sorted(required - set(LAMBDA_SPECS[name]["sources"]))
    assert not missing, f"{name} imports modules its zip would not contain: {missing}"


def test_every_lambda_handler_has_a_packaging_spec():
    handlers = {
        p.parent.name for p in (ROOT / "backend" / "lambdas").glob("*/handler.py")
    }
    assert handlers - set(LAMBDA_SPECS) == set()


# Reproducible builds: unchanged code must give a
# byte-identical zip, or `terraform plan` reports every Lambda as changed.


def _staging(tmp_path, files):
    staging = tmp_path / "staging"
    for rel, content in files.items():
        f = staging / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content)
    return staging


def test_zip_is_byte_identical_across_builds(tmp_path):
    import os
    import time

    staging = _staging(tmp_path, {"b/handler.py": b"x = 1\n", "a.py": b"y = 2\n"})
    PACKAGER._zip_staging_dir(staging, tmp_path / "one.zip")
    # A later rebuild: same content, newer modification times.
    later = time.time() + 3600
    for f in staging.rglob("*.py"):
        os.utime(f, (later, later))
    PACKAGER._zip_staging_dir(staging, tmp_path / "two.zip")
    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()


def test_zip_entries_use_forward_slashes_and_sorted_order(tmp_path):
    import zipfile

    staging = _staging(tmp_path, {"b/handler.py": b"", "a.py": b""})
    PACKAGER._zip_staging_dir(staging, tmp_path / "out.zip")
    assert zipfile.ZipFile(tmp_path / "out.zip").namelist() == ["a.py", "b/handler.py"]


def test_every_pin_is_exact():
    pins = PACKAGER.pinned_versions()
    assert {"pydantic", "python-hcl2"} <= set(pins)
    assert all(pins.values())


def test_every_spec_package_is_pinned():
    pins = PACKAGER.pinned_versions()
    for name, spec in LAMBDA_SPECS.items():
        for requirement in spec["packages"]:
            pkg = PACKAGER._normalize(requirement.split(">")[0].split("=")[0])
            assert pkg in pins, f"{name}: {requirement} has no pin"


def test_unpinned_bundled_package_fails_the_build(tmp_path):
    constraints = tmp_path / "c.txt"
    constraints.write_text("pydantic==2.14.1\n", encoding="utf-8")
    staging = _staging(tmp_path, {"pydantic-2.14.1.dist-info/METADATA": b""})
    PACKAGER.check_all_pinned(staging, constraints)  # pinned: fine

    (staging / "surprise_pkg-1.0.dist-info").mkdir()
    with pytest.raises(SystemExit, match="surprise_pkg"):
        PACKAGER.check_all_pinned(staging, constraints)


def test_wrong_version_fails_the_build(tmp_path):
    constraints = tmp_path / "c.txt"
    constraints.write_text("pydantic==2.14.1\n", encoding="utf-8")
    staging = _staging(tmp_path, {"pydantic-2.15.0.dist-info/METADATA": b""})
    with pytest.raises(SystemExit, match="pydantic"):
        PACKAGER.check_all_pinned(staging, constraints)


def test_sdk_feature_users_bundle_the_pinned_boto3():
    # It calls S3 Vectors, which an older runtime boto3 doesn't know
    # Conditional/checksum S3 uploads and AgentCore also need a known SDK.
    assert "boto3" in LAMBDA_SPECS["ask_question"]["packages"]
    others = [
        n
        for n, s in LAMBDA_SPECS.items()
        if n != "ask_question" and "boto3" in s["packages"]
    ]
    assert set(others) == {"create_upload", "submit_review", "review_worker", "deeper_review"}
    assert PACKAGER.pinned_versions()["boto3"] == "1.43.96"
