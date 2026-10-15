"""Packaging regression tests (Codex F23).

scripts/package_lambdas.py lists each Lambda's source files by hand. A
handler that gained a `backend.*` import without the spec being updated
deployed fine and then failed at cold start with ModuleNotFoundError
(kill_switch, then report.py for deeper_review). These tests walk each
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


LAMBDA_SPECS = _load_package_script().LAMBDA_SPECS


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
