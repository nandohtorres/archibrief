"""Builds the Lambda layer that carries the Trivy binary (ADR-0048).

    python scripts/build_trivy_layer.py

Downloads one pinned Trivy release, checks it against the SHA-256 pinned
below (taken from Aqua's published checksums file for that release), and
writes backend/build/trivy-layer.zip with the binary at bin/trivy, which
Lambda mounts as /opt/bin/trivy.

Size alarm: a function plus its layers must stay under Lambda's 250 MB
unzipped limit. The build fails above SIZE_BUDGET_BYTES, well before
that, so a future Trivy upgrade that grows too large is caught here
rather than at deploy time. The fix at that point is moving the Scan
Lambda to a container image (10 GB limit); see ADR-0048.

To upgrade Trivy: change TRIVY_VERSION, take the new Linux-64bit
SHA-256 from trivy_<version>_checksums.txt on the release page, update
TRIVY_SHA256, rebuild, and re-run the trap suite.
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "backend" / "build" / "trivy-layer.zip"
SCAN_PACKAGE = ROOT / "backend" / "lambdas" / "scan" / "build" / "scan.zip"

TRIVY_VERSION = "0.76.0"
TRIVY_ASSET = f"trivy_{TRIVY_VERSION}_Linux-64bit.tar.gz"
TRIVY_SHA256 = "e24b1c51293c1b15e4ba8d45bbc7891ba053f90278ec2698f3562c993e145fe7"
TRIVY_URL = f"https://github.com/aquasecurity/trivy/releases/download/v{TRIVY_VERSION}/{TRIVY_ASSET}"

LAMBDA_UNZIPPED_LIMIT_BYTES = 250 * 1024 * 1024
SIZE_BUDGET_BYTES = 230 * 1024 * 1024


class BuildError(Exception):
    pass


def verify_sha256(data: bytes, expected: str = TRIVY_SHA256) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise BuildError(
            f"checksum mismatch for {TRIVY_ASSET}: expected {expected}, got {actual}"
        )


def extract_binary(archive_bytes: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        member = archive.getmember("trivy")
        if not member.isfile():
            raise BuildError("trivy entry in the release archive is not a regular file")
        handle = archive.extractfile(member)
        if handle is None:
            raise BuildError("could not read trivy from the release archive")
        return handle.read()


def unzipped_size(zip_path: Path) -> int:
    with zipfile.ZipFile(zip_path) as archive:
        return sum(info.file_size for info in archive.infolist())


def check_size_budget(binary_size: int, function_size: int) -> int:
    """Total unzipped bytes; raises when the budget is exceeded."""
    total = binary_size + function_size
    if total > SIZE_BUDGET_BYTES:
        raise BuildError(
            f"Scan Lambda would be {total / 2**20:.0f} MiB unzipped, over the "
            f"{SIZE_BUDGET_BYTES / 2**20:.0f} MiB budget (Lambda's limit is "
            f"{LAMBDA_UNZIPPED_LIMIT_BYTES / 2**20:.0f} MiB). Move the Scan Lambda to a "
            "container image (ADR-0048)."
        )
    return total


def write_layer(binary: bytes, output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo("bin/trivy", date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100755 & 0xFFFF) << 16  # regular file, executable
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, binary, compresslevel=9)


def main() -> None:
    print(f"Downloading {TRIVY_URL}")
    with urllib.request.urlopen(TRIVY_URL, timeout=120) as response:
        archive_bytes = response.read()
    verify_sha256(archive_bytes)
    binary = extract_binary(archive_bytes)

    function_size = unzipped_size(SCAN_PACKAGE) if SCAN_PACKAGE.exists() else 0
    if not function_size:
        print("note: scan.zip not built yet; size check covers the binary only")
    total = check_size_budget(len(binary), function_size)

    write_layer(binary)
    print(
        f"{OUTPUT} ({OUTPUT.stat().st_size / 2**20:.1f} MiB zipped); Scan Lambda total "
        f"{total / 2**20:.0f} MiB of the {SIZE_BUDGET_BYTES / 2**20:.0f} MiB budget"
    )


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        sys.exit(f"error: {exc}")
