import io
import os
import tarfile

import pytest

from backend.lambdas.ingest.handler import (
    IngestRejected,
    extract_archive,
    parse_terraform_files,
)


def _make_archive(path: str, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_extract_rejects_path_traversal(tmp_path):
    archive_path = str(tmp_path / "evil.tar")
    _make_archive(archive_path, {"../../etc/passwd": b"x"})
    with pytest.raises(IngestRejected, match="path traversal"):
        extract_archive(archive_path, str(tmp_path / "out"))


def test_extract_rejects_symlink(tmp_path):
    archive_path = str(tmp_path / "evil.tar")
    with tarfile.open(archive_path, "w") as archive:
        info = tarfile.TarInfo(name="main.tf")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(IngestRejected, match="symlink"):
        extract_archive(archive_path, str(tmp_path / "out"))


def test_extract_rejects_too_many_members(tmp_path):
    archive_path = str(tmp_path / "bomb.tar")
    members = {f"file{i}.tf": b"x" for i in range(600)}
    _make_archive(archive_path, members)
    with pytest.raises(IngestRejected, match="too many members"):
        extract_archive(archive_path, str(tmp_path / "out"))


def test_extract_accepts_valid_terraform(tmp_path):
    archive_path = str(tmp_path / "good.tar")
    _make_archive(archive_path, {"main.tf": b'resource "aws_s3_bucket" "x" {}'})
    dest = str(tmp_path / "out")
    extracted = extract_archive(archive_path, dest)
    assert len(extracted) == 1
    assert extracted[0].endswith("main.tf")


def test_parse_terraform_files_reads_resources(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(
        'resource "aws_s3_bucket" "data" {\n  bucket = "my-bucket"\n}\n'
    )
    parsed = parse_terraform_files([str(tf_file)])
    assert "aws_s3_bucket" in parsed.resources
    assert "data" in parsed.resources["aws_s3_bucket"]


def test_parse_terraform_flags_remote_module_not_observable(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(
        'resource "aws_lambda_function" "fn" {\n'
        '  source = "git::https://example.com/module.git"\n'
        "}\n"
    )
    parsed = parse_terraform_files([str(tf_file)])
    assert "aws_lambda_function.fn" in parsed.not_observable


def test_ingest_module_has_no_terraform_subprocess_dependency():
    import ast
    import backend.lambdas.ingest.handler as handler_module

    source = ast.parse(open(handler_module.__file__).read())
    imported_names = set()
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    assert "subprocess" not in imported_names
    assert "os.system" not in imported_names
