"""Builds the ZIP deployment package for AgentCore Runtime's ZIP/
code_configuration deployment path (infra/modules/agentcore-runtime).

Design notes:
- Only pydantic/boto3/langgraph/bedrock-agentcore are actually imported by
  anything reachable from runtime_entrypoint.py. beautifulsoup4, pypdf and
  python-hcl2 are ingestion-only and are not packaged.
- AgentCore Runtime is ARM64-only and validates every native .so's ELF
  header, so a Windows or x86_64-built wheel fails deployment outright.
  Dependencies are installed via `uv pip install --python-platform
  aarch64-manylinux2014`, not plain `pip`, because `pip download
  --platform` has an open bug
  (pypa/pip#13442/#11664/#6117): it filters wheel tags for the target
  platform but evaluates dependency environment markers against the HOST
  machine, so a Linux-only conditional dependency could silently be
  skipped when resolving from Windows. `uv` is what AWS's docs use and does
  not have this bug.
- Only backend/corpus/data/chunks/ (5.7MB, read by lexical_index.py) is
  needed at runtime, not backend/corpus/data/raw/ (17MB of ingestion-only
  source content) or embed_checkpoint.json.
- Only .py files are copied from backend/agent, backend/shared,
  backend/corpus — NOT a blind directory copy, because backend/build/
  (staging + vendor artifacts for the OTHER lambda zips) sits right next
  to backend/agent as a sibling directory and would otherwise get swept
  in. Ingestion .py files (normalize_pdf.py etc.) are included but never
  imported, so their unmet dependencies don't matter.
- ZIP entries get explicit Unix metadata (create_system=3, S_IFREG|0o644
  for files, S_IFDIR|0o755 for directories with a trailing "/", explicit
  ZIP_DEFLATED compression) because (a) a manually-constructed ZipInfo
  defaults to ZIP_STORED, and (b) AgentCore Runtime needs 644/755 Unix
  permissions on extraction, which a Windows-built zip does not set by
  default.
- Dependencies are pinned via runtime_requirements.lock.txt (compiled with
  `uv pip compile --python-platform aarch64-manylinux2014 --python-version
  3.12`), not a bare `uv pip install <package names>`, for build
  reproducibility — a future run shouldn't silently resolve different
  transitive versions than a prior one.

Known limitation, not solved by this script: a real Python `import` smoke
test of the assembled package is NOT possible on Windows, because
pydantic's compiled core (and other native extensions) are ARM64 ELF
binaries that cannot load on a Windows/x86_64 host regardless of whether
the package layout is correct. This script verifies structure (exact
archive paths, presence of the entry point, .py files parse without
SyntaxError) but genuine import-resolution correctness can only be
confirmed by a real AgentCore deployment.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
_AGENT_DIR = _BACKEND_DIR / "agent"
_LOCK_FILE = _AGENT_DIR / "runtime_requirements.lock.txt"
_REQUIREMENTS_IN = _AGENT_DIR / "runtime_requirements.in"

_BUILD_ROOT = _AGENT_DIR / "build"
_OUTPUT_ZIP = _BUILD_ROOT / "agentcore-runtime.zip"

# Staging MUST live outside backend/ entirely — backend/agent is one of the
# trees _copy_source_tree scans with rglob("*.py"), so a staging dir nested
# anywhere under backend/ gets picked up mid-scan by its own source walk
# and recursively copies itself into itself until Windows' path-length limit
# stops it.
_STAGING_DIR = Path(tempfile.mkdtemp(prefix="archibrief-agentcore-build-"))

_ENTRY_POINT = "backend/agent/runtime_entrypoint.py"

# Which backend/ subtrees get their .py files copied in, and which data
# files travel alongside them. Deliberately NOT backend/lambdas,
# backend/build, backend/.venv — see module docstring.
_SOURCE_SUBTREES = ("agent", "shared", "corpus")
_CHUNKS_DIR = _BACKEND_DIR / "corpus" / "data" / "chunks"

_MAX_ZIPPED_BYTES = 250 * 1024 * 1024
_MAX_UNZIPPED_BYTES = 750 * 1024 * 1024


class PackageTooLarge(Exception):
    pass


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=_REPO_ROOT)


def relock() -> None:
    """Regenerate runtime_requirements.lock.txt from runtime_requirements.in.

    Run this deliberately when the .in bounds change or a fresh dependency
    refresh is wanted — not automatically on every build, so builds stay
    reproducible against whatever was last locked.
    """
    _run(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "compile",
            "--python-platform",
            "aarch64-manylinux2014",
            "--python-version",
            "3.12",
            str(_REQUIREMENTS_IN),
            "-o",
            str(_LOCK_FILE),
        ]
    )


def _install_dependencies(target_dir: Path) -> None:
    if not _LOCK_FILE.exists():
        raise FileNotFoundError(
            f"{_LOCK_FILE} does not exist — run with --relock first to generate it."
        )
    _run(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            "--python-platform",
            "aarch64-manylinux2014",
            "--python-version",
            "3.12",
            "--target",
            str(target_dir),
            "--only-binary=:all:",
            "-r",
            str(_LOCK_FILE),
        ]
    )


def _strip_install_artifacts(target_dir: Path) -> None:
    """`uv pip install --target` drops host-platform build/launcher
    artifacts alongside the actual packages — a .lock marker file and a
    bin/ directory of Windows .exe console-script launchers (httpx.exe,
    uvicorn.exe, etc.). Neither is imported by our code, and the .exe files
    are the wrong architecture for the Linux ARM64 target. Strip both so they
    don't add dead weight or risk tripping AgentCore's native-binary
    validation."""
    lock_file = target_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    bin_dir = target_dir / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)


def _copy_source_tree(target_dir: Path) -> list[Path]:
    """Copies only .py files from the source subtrees, preserving relative
    layout under target_dir/backend/... Returns every copied file's path
    for the later syntax-check pass."""
    copied: list[Path] = []
    init_file = _BACKEND_DIR / "__init__.py"
    dest_init = target_dir / "backend" / "__init__.py"
    dest_init.parent.mkdir(parents=True, exist_ok=True)
    if init_file.exists():
        shutil.copy2(init_file, dest_init)
    else:
        dest_init.touch()
    copied.append(dest_init)

    for subtree in _SOURCE_SUBTREES:
        src_root = _BACKEND_DIR / subtree
        for py_file in src_root.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            rel = py_file.relative_to(_BACKEND_DIR)
            dest = target_dir / "backend" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(py_file, dest)
            copied.append(dest)
    return copied


def _copy_chunk_data(target_dir: Path) -> None:
    dest_dir = target_dir / "backend" / "corpus" / "data" / "chunks"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for chunk_file in _CHUNKS_DIR.glob("*.json"):
        shutil.copy2(chunk_file, dest_dir / chunk_file.name)


def _check_syntax(py_files: list[Path]) -> None:
    errors: list[str] = []
    for py_file in py_files:
        try:
            compile(py_file.read_text(encoding="utf-8"), str(py_file), "exec")
        except SyntaxError as exc:
            errors.append(f"{py_file}: {exc}")
    if errors:
        raise SyntaxError("Syntax errors in staged files:\n" + "\n".join(errors))


def _total_uncompressed_size(root_dir: Path) -> int:
    return sum(f.stat().st_size for f in root_dir.rglob("*") if f.is_file())


def _write_zip(staging_dir: Path, dest_zip: Path) -> None:
    """Zips staging_dir's contents at the archive root with explicit Unix
    metadata — a manually-built ZipInfo defaults to ZIP_STORED and no Unix
    permission bits, neither of which AWS's AgentCore Runtime tolerates
    correctly by default on a Windows-built archive."""
    tmp_zip = dest_zip.with_suffix(".zip.tmp")
    if tmp_zip.exists():
        tmp_zip.unlink()

    entries = sorted(staging_dir.rglob("*"))
    with zipfile.ZipFile(tmp_zip, "w") as zf:
        # Explicit directory entries first so extraction tools that rely on
        # them (rather than inferring dirs from file paths) get correct
        # permissions too.
        seen_dirs: set[str] = set()
        for entry in entries:
            rel = entry.relative_to(staging_dir).as_posix()
            if entry.is_dir():
                arcname = rel + "/"
                if arcname in seen_dirs:
                    continue
                seen_dirs.add(arcname)
                info = zipfile.ZipInfo(arcname)
                info.create_system = 3  # Unix
                info.external_attr = (stat.S_IFDIR | 0o755) << 16
                zf.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(rel)
                info.create_system = 3  # Unix
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, entry.read_bytes())

    zipped_size = tmp_zip.stat().st_size
    if zipped_size > _MAX_ZIPPED_BYTES:
        tmp_zip.unlink()
        raise PackageTooLarge(
            f"Zipped package is {zipped_size} bytes, over the "
            f"{_MAX_ZIPPED_BYTES}-byte (250MB) AgentCore Runtime limit."
        )

    with zipfile.ZipFile(tmp_zip) as zf:
        names = zf.namelist()
    if _ENTRY_POINT not in names:
        tmp_zip.unlink()
        raise AssertionError(
            f"{_ENTRY_POINT!r} is not present at the expected archive path. "
            f"Present backend/agent/*.py entries: "
            f"{[n for n in names if n.startswith('backend/agent/') and n.endswith('.py')]}"
        )

    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    if dest_zip.exists():
        dest_zip.unlink()
    tmp_zip.rename(dest_zip)


def build() -> Path:
    try:
        return _build_in(_STAGING_DIR)
    finally:
        shutil.rmtree(_STAGING_DIR, ignore_errors=True)


def _build_in(staging_dir: Path) -> Path:
    print("Installing pinned runtime dependencies (ARM64/Python 3.12)...")
    _install_dependencies(staging_dir)

    print("Stripping host-platform install artifacts (.lock, bin/)...")
    _strip_install_artifacts(staging_dir)

    print("Copying backend source (.py files only)...")
    copied_py_files = _copy_source_tree(staging_dir)

    print("Copying corpus chunk data...")
    _copy_chunk_data(staging_dir)

    print("Checking staged .py files for syntax errors...")
    _check_syntax(copied_py_files)

    uncompressed_size = _total_uncompressed_size(staging_dir)
    if uncompressed_size > _MAX_UNZIPPED_BYTES:
        raise PackageTooLarge(
            f"Uncompressed staged package is {uncompressed_size} bytes, over the "
            f"{_MAX_UNZIPPED_BYTES}-byte (750MB) AgentCore Runtime limit."
        )
    print(f"Uncompressed size: {uncompressed_size / 1024 / 1024:.1f} MB")

    print("Writing ZIP with explicit Unix metadata...")
    _write_zip(staging_dir, _OUTPUT_ZIP)

    zipped_size = _OUTPUT_ZIP.stat().st_size
    print(f"Zipped size: {zipped_size / 1024 / 1024:.1f} MB")
    print(f"Wrote {_OUTPUT_ZIP}")

    return _OUTPUT_ZIP


if __name__ == "__main__":
    if "--relock" in sys.argv:
        relock()
    build()
