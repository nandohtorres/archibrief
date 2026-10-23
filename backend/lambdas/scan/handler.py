"""ArchiBrief Lambda: scan (ADR-0048).

Runs Trivy, an established open-source IaC scanner, over the submitted
Terraform and returns only the results for checks ArchiBrief trusts
(backend/shared/trivy_checks.py). The rule engine turns those into
findings alongside its own rules.

This is the one place ArchiBrief runs a subprocess on submitted content,
so it is boxed in on every side:
- It is its own Lambda with read-only access to uploads/ and nothing else.
- Trivy runs with a clean environment: no AWS credentials, and HTTP(S)
  proxies pointed at a closed local port, so it can't reach the network.
- Before scanning, every `source = "..."` that isn't a local path inside
  the archive is rewritten. Trivy otherwise downloads remote modules named
  by the submitter, which would let them make this service fetch
  arbitrary URLs.
- Trivy only parses and evaluates HCL statically. It never runs terraform,
  providers, or provisioners.
- Any failure returns status "unavailable": the review continues on
  ArchiBrief's own rules and the report says the scanner didn't run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath

import hcl2

from backend.shared.archive import IngestRejected, extract_archive
from backend.shared.clients import S3Client
from backend.shared.terraform_scope import scoped_key
from backend.shared.trivy_checks import TRUSTED_CHECK_IDS, TRUSTED_CHECKS

DEFAULT_TRIVY_PATH = "/opt/bin/trivy"
SCAN_TIMEOUT_SECONDS = 60
MAX_RESULTS = 200
NEUTRALIZED_SOURCE = "./.archibrief-remote-module-removed"
# A port nothing listens on: any HTTP(S) request Trivy attempts fails fast.
_DEAD_PROXY = "http://127.0.0.1:9"

_RESOURCE_TYPE = re.compile(r"^[a-z0-9_]+$")
_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
# count / for_each instances: name[0] or name["key"]. The findings are
# about the resource block, so the index is dropped.
_INSTANCE_INDEX = re.compile(r'\[(?:\d+|"(?:[^"\\]|\\.)*")\]')


def _log(review_id: str | None, stage: str, **fields: object) -> None:
    print(json.dumps({"lambda": "scan", "review_id": review_id, "stage": stage, **fields}))


def _is_local_inside(source: str, file_dir: Path, root: Path) -> bool:
    if not source.startswith(("./", "../")):
        return False
    target = (file_dir / source).resolve()
    return target == root or root in target.parents


def neutralize_remote_sources(files: list[str], root: str) -> int:
    """Rewrite non-local `source` attributes in place. Returns how many changed."""
    root_path = Path(root).resolve()
    changed = 0
    for file in files:
        path = Path(file)
        if path.suffix != ".tf":
            continue
        file_dir = path.parent.resolve()
        with path.open(encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
        # Positions come from the real grammar: braces in comments, strings
        # and heredocs are not blocks. An unparseable source fails before
        # Trivy starts, rather than trusting incomplete sanitization.
        try:
            tree = hcl2.parses(text).to_lark()
        except Exception:  # noqa: BLE001 - parser failures must stop scanning without echoing input
            raise ValueError("unsupported HCL for isolated scanning") from None
        replacements = []
        for block in tree.find_data("block"):
            if str(block.children[0].children[0]) != "module":
                continue
            body = next(child for child in block.children if getattr(child, "data", None) == "body")
            attributes = [
                child
                for child in body.children
                if getattr(child, "data", None) == "attribute"
                and str(child.children[0].children[0]) == "source"
            ]
            if len(attributes) != 1:
                raise ValueError("module source cannot be neutralized safely")
            expression = attributes[0].children[-1]
            start, end = expression.meta.start_pos, expression.meta.end_pos
            raw = text[start:end]
            try:
                source = json.loads(raw)
            except (ValueError, TypeError):
                source = None
            if (
                isinstance(source, str)
                and "${" not in source
                and "%{" not in source
                and _is_local_inside(source, file_dir, root_path)
            ):
                continue
            replacement = json.dumps(NEUTRALIZED_SOURCE) + "\n" * raw.count("\n")
            replacements.append((start, end, replacement))
        new_text = text
        for start, end, replacement in sorted(replacements, reverse=True):
            new_text = new_text[:start] + replacement + new_text[end:]
        changed += len(replacements)
        if new_text != text:
            with path.open("w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
    return changed


def _trivy_env(cache_dir: str) -> dict[str, str]:
    env = {
        "HOME": cache_dir,
        "TMPDIR": cache_dir,
        "TMP": cache_dir,
        "TEMP": cache_dir,
        "HTTP_PROXY": _DEAD_PROXY,
        "HTTPS_PROXY": _DEAD_PROXY,
        "http_proxy": _DEAD_PROXY,
        "https_proxy": _DEAD_PROXY,
        "NO_PROXY": "",
        "no_proxy": "",
    }
    # Windows needs these to start a process at all (local test runs only).
    for name in ("SYSTEMROOT", "SystemRoot", "PATH"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def run_trivy(scan_dir: str, trivy_path: str, timeout: int = SCAN_TIMEOUT_SECONDS) -> dict:
    cache_dir = tempfile.mkdtemp(prefix="archibrief-trivy-cache-")
    try:
        completed = subprocess.run(
            [
                trivy_path,
                "config",
                "--skip-check-update",
                "--skip-version-check",
                "--disable-telemetry",
                "--misconfig-scanners",
                "terraform",
                "--cache-dir",
                cache_dir,
                "--format",
                "json",
                "--quiet",
                "--exit-code",
                "0",
                scan_dir,
            ],
            capture_output=True,
            timeout=timeout,
            env=_trivy_env(cache_dir),
            check=False,
        )
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
    if completed.returncode != 0:
        raise RuntimeError(f"trivy exited with {completed.returncode}")
    return json.loads(completed.stdout)


def _module_for(target: Path, root: Path) -> str:
    relative = os.path.relpath(target.parent, root)
    return "" if relative == "." else PurePosixPath(*Path(relative).parts).as_posix()


def trusted_results(
    report: dict, scan_dir: str, files: list[str], *, bounded: bool = True
) -> list[dict]:
    """Keep only trusted, failing checks, as small identifier-only records."""
    directories = [os.path.dirname(os.path.abspath(f)) for f in files]
    module_root = Path(os.path.commonpath(directories)) if directories else Path(scan_dir)
    results: list[dict] = []
    for result in report.get("Results") or []:
        target = Path(scan_dir) / result.get("Target", "")
        for item in result.get("Misconfigurations") or []:
            check_id = item.get("ID")
            if item.get("Status") != "FAIL" or check_id not in TRUSTED_CHECK_IDS:
                continue
            cause = item.get("CauseMetadata") or {}
            address = _INSTANCE_INDEX.sub("", str(cause.get("Resource", "")))
            if re.fullmatch(r"module\.[A-Za-z0-9_-]+(?:\.module\.[A-Za-z0-9_-]+)*", address):
                results.append(
                    {
                        "check_id": check_id,
                        "scope": "module",
                        "resource_key": "/".join(address.split(".")[1::2]),
                        "file": PurePosixPath(*Path(result.get("Target", "")).parts).as_posix(),
                        "start_line": int(cause.get("StartLine") or 0),
                        "end_line": int(cause.get("EndLine") or 0),
                    }
                )
                continue
            resource_type, _, name = address.rpartition(".")
            # Module-called resources come back as module.x.type.name; the
            # last two segments identify the resource.
            resource_type = resource_type.rpartition(".")[2]
            if not (_RESOURCE_TYPE.match(resource_type) and _RESOURCE_NAME.match(name)):
                continue
            module = _module_for(target.resolve(), module_root.resolve())
            results.append(
                {
                    "check_id": check_id,
                    "resource_type": resource_type,
                    "resource_key": scoped_key(module, name),
                    "file": PurePosixPath(*Path(result.get("Target", "")).parts).as_posix(),
                    "start_line": int(cause.get("StartLine") or 0),
                    "end_line": int(cause.get("EndLine") or 0),
                    **({"module_origin": True} if address.startswith("module.") else {}),
                }
            )
    # Keep one result for each concern before retaining more of a noisy
    # concern. Input order must not let hundreds of bucket checks hide RDS.
    if len(results) <= MAX_RESULTS:
        return results
    first, rest, seen = [], [], set()
    for result in results:
        concern = TRUSTED_CHECKS[result["check_id"]].concern
        (rest if concern in seen else first).append(result)
        seen.add(concern)
    ordered = first + rest
    return ordered[:MAX_RESULTS] if bounded else ordered


def scan_files(scan_dir: str, files: list[str], trivy_path: str | None = None) -> dict:
    """Neutralize, run Trivy, and filter. Used by the handler and the trap suite."""
    trivy_path = trivy_path or os.environ.get("TRIVY_PATH", DEFAULT_TRIVY_PATH)
    if not os.path.exists(trivy_path):
        return {"status": "unavailable", "tool": "trivy", "reason": "scanner_not_installed"}
    neutralized = neutralize_remote_sources(files, scan_dir)
    report = run_trivy(scan_dir, trivy_path)
    results = trusted_results(report, scan_dir, files, bounded=False)
    return {
        "status": "ok",
        "tool": "trivy",
        "version": os.environ.get("TRIVY_VERSION", "unknown"),
        "neutralized_sources": neutralized,
        "results": results[:MAX_RESULTS],
        "results_total": len(results),
        "truncated": len(results) > MAX_RESULTS,
    }


def handler(event: dict, _context: object, s3_client: S3Client | None = None) -> dict:
    review_id = event.get("review_id")
    started = time.monotonic()
    work_dir = tempfile.mkdtemp(prefix="archibrief-scan-")
    try:
        client = s3_client or S3Client(bucket=event["report_bucket"])
        archive_path = os.path.join(work_dir, "archive.tar")
        with open(archive_path, "wb") as fh:
            version = event.get("archive_s3_version")
            fh.write(
                client.get_object(event["archive_s3_key"], version_id=version)
                if version
                else client.get_object(event["archive_s3_key"])
            )
        scan_dir = os.path.join(work_dir, "files")
        files = extract_archive(archive_path, scan_dir)
        result = scan_files(scan_dir, files)
    except IngestRejected:
        # Ingest already rejects these; the scanner has nothing to add.
        result = {"status": "unavailable", "tool": "trivy", "reason": "archive_rejected"}
    except subprocess.TimeoutExpired:
        result = {"status": "unavailable", "tool": "trivy", "reason": "timeout"}
    except Exception as exc:  # noqa: BLE001 — the review continues without the scanner
        result = {"status": "unavailable", "tool": "trivy", "reason": type(exc).__name__}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    _log(
        review_id,
        "done",
        status=result["status"],
        reason=result.get("reason"),
        results=len(result.get("results", [])),
        seconds=round(time.monotonic() - started, 2),
    )
    return result
