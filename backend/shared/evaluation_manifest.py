"""Offline evaluation fingerprints. No SDK clients, shell commands or raw cases."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            checksum.update(block)
    return checksum.hexdigest()


def revision(root: Path) -> str | None:
    """Read an ordinary independent checkout only; never follow worktree links."""
    git = root / ".git"
    if not git.is_dir():
        return None
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            if not re.fullmatch(r"refs/[A-Za-z0-9_./-]+", ref) or ".." in Path(ref).parts:
                return None
            loose = git / ref
            if loose.is_file():
                head = loose.read_text(encoding="utf-8").strip()
            else:
                packed = git / "packed-refs"
                lines = packed.read_text(encoding="utf-8").splitlines() if packed.is_file() else []
                head = next((line.split()[0] for line in lines if line.endswith(" " + ref)), "")
        return head if re.fullmatch(r"[0-9a-f]{40}", head) else None
    except OSError:
        return None


def build_manifest(cases, configuration, *, root: Path = ROOT) -> dict:
    files = {}
    unavailable = []

    # Skip vendored dependencies, corpus payloads and caches before traversal.
    def walk_error(error):
        failed = Path(error.filename) if error.filename else root / "backend"
        unavailable.append(
            failed.relative_to(root).as_posix()
            if failed.is_relative_to(root)
            else "source_directory_unavailable"
        )

    for directory, children, names in os.walk(root / "backend", onerror=walk_error):
        children[:] = sorted(
            child for child in children if child not in {"build", "data", "__pycache__", ".venv"}
        )
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix not in {".py", ".json", ".toml"} and not name.endswith(".lock.txt"):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                files[relative] = file_digest(path)
            except OSError:
                unavailable.append(relative)
    extras = list((root / "tests/backend/adversarial").glob("*.json")) + list(
        (root / "tests/backend/adversarial").glob("*.py")
    )
    extras += list((root / "tests/backend/adversarial/fixtures").rglob("*.tf"))
    extras += list((root / "frontend/public/demos").rglob("*.json"))
    rubric = root / "tests/backend/adversarial/model_eval/SCORING.md"
    if rubric.is_file():
        extras.append(rubric)
    for path in sorted(extras):
        relative = path.relative_to(root).as_posix()
        try:
            files[relative] = file_digest(path)
        except OSError:
            unavailable.append(relative)
    corpus = {}
    for path in sorted((root / "backend/corpus/data/chunks").glob("*.json")):
        try:
            corpus[path.name] = file_digest(path)
        except OSError:
            unavailable.append(path.relative_to(root).as_posix())
    installed = {}
    for package in ("boto3", "botocore", "langgraph", "pydantic", "python-hcl2"):
        try:
            installed[package] = version(package)
        except PackageNotFoundError:
            installed[package] = None
    return {
        "version": "evaluation-manifest@1",
        "git_revision": revision(root),
        "working_source_sha256": digest(files),
        "file_sha256": files,
        "unavailable_files": unavailable,
        "source_complete": bool(files) and not unavailable,
        "selected_cases_sha256": digest(cases),
        "selected_set_sizes": {name: len(items) for name, items in cases.items()},
        "configuration": configuration,
        "corpus_files_sha256": corpus,
        "local_corpus_available": bool(corpus),
        "live_index_verified": False,
        "python_version": platform.python_version(),
        "installed_versions": installed,
        "semantic_grading": "not_established_by_manifest",
    }


def attach_manifest(args, cases, configuration) -> None:
    # The same immutable start-of-run metadata reaches preview and journal.
    args.evaluation_manifest = build_manifest(cases, configuration)
    from backend.agent.nodes.reason import PROMPT_VERSION as reason_version
    from backend.chat.prompt import PROMPT_VERSION as chat_version
    from backend.shared.models.finding import Finding

    args.evaluation_manifest["contracts"] = {
        "reason_prompt": reason_version,
        "chat_prompt": chat_version,
        "finding_schema_sha256": digest(Finding.model_json_schema()),
    }


def evidence_manifest(chunks) -> dict:
    """Record bounded evidence identity, not source text, URLs or prompts."""
    records = []
    for chunk in chunks[:64]:
        chunk = chunk if isinstance(chunk, dict) else {}
        record = {}
        for key in ("chunk_id", "document_id", "corpus_version", "parser_version"):
            value = chunk.get(key)
            record[key] = (
                value
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,180}", value)
                else None
            )
        checksum = chunk.get("content_hash")
        record["content_hash"] = (
            checksum
            if isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum)
            else None
        )
        timestamp = chunk.get("retrieved_at")
        try:
            record["retrieved_at"] = (
                datetime.fromisoformat(timestamp).isoformat()
                if isinstance(timestamp, str)
                else None
            )
        except ValueError:
            record["retrieved_at"] = None
        records.append(record)
    return {
        "count": len(chunks),
        "omitted": max(0, len(chunks) - 64),
        "chunks": records,
        "source_content_verified": False,
    }
