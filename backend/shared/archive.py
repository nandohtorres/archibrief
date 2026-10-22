"""Safe extraction of a submitted Terraform archive.

Shared by Ingest (which parses the files) and Scan (which runs Trivy on
them, ADR-0048), so both read exactly the same, already-vetted set of
files. Extraction is static: nothing in the archive is executed.
"""

from __future__ import annotations

import os
import tarfile
from pathlib import PurePosixPath

MAX_ARCHIVE_MEMBERS = 500
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".tf", ".tfvars", ".hcl"}


class IngestRejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _reject_unsafe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if name.startswith("/") or ".." in PurePosixPath(name).parts:
        raise IngestRejected(f"path traversal in archive member: {name}")
    if member.issym() or member.islnk():
        raise IngestRejected(f"symlink/hardlink not allowed: {name}")
    if member.isdev():
        raise IngestRejected(f"device file not allowed: {name}")
    if member.size > MAX_MEMBER_BYTES:
        raise IngestRejected(f"archive member too large: {name}")


def extract_archive(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a submitted Terraform archive, statically, with no code execution.

    Rejects path traversal, symlink escapes, archive bombs, oversized
    members, and non-text file types outside the allowlist.
    """
    extracted: list[str] = []
    total_uncompressed = 0

    with tarfile.open(archive_path, mode="r:*") as archive:
        # Iterate rather than getmembers(): limits are enforced as each
        # header is read, so an archive with a huge member count is
        # rejected at member 501 instead of after scanning every header.
        members: list[tarfile.TarInfo] = []
        for member in archive:
            members.append(member)
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise IngestRejected("archive contains too many members")
            _reject_unsafe_member(member)
            total_uncompressed += max(member.size, 0)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise IngestRejected("archive exceeds uncompressed size limit")

        for member in members:
            if not member.isfile():
                continue
            suffix = PurePosixPath(member.name).suffix
            basename = PurePosixPath(member.name).name
            variable_json = basename == "terraform.tfvars.json" or basename.endswith(".auto.tfvars.json")
            if suffix not in ALLOWED_SUFFIXES and not variable_json:
                continue
            archive.extract(member, path=dest_dir, filter="data")
            extracted.append(os.path.join(dest_dir, member.name))

    if not extracted:
        raise IngestRejected("archive contained no .tf/.tfvars/.hcl files")
    return extracted
