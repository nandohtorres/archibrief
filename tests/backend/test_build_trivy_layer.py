import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import build_trivy_layer as layer  # noqa: E402


def test_checksum_mismatch_fails_the_build():
    with pytest.raises(layer.BuildError, match="checksum mismatch"):
        layer.verify_sha256(
            b"tampered", expected=hashlib.sha256(b"original").hexdigest()
        )


def test_matching_checksum_passes():
    layer.verify_sha256(b"original", expected=hashlib.sha256(b"original").hexdigest())


def test_size_alarm_trips_before_lambdas_limit():
    assert layer.SIZE_BUDGET_BYTES < layer.LAMBDA_UNZIPPED_LIMIT_BYTES
    assert layer.check_size_budget(175 * 2**20, 20 * 2**20) == 195 * 2**20
    with pytest.raises(layer.BuildError, match="container image"):
        layer.check_size_budget(225 * 2**20, 10 * 2**20)


def test_layer_puts_an_executable_binary_at_bin_trivy(tmp_path):
    output = tmp_path / "layer.zip"
    layer.write_layer(b"\x7fELF fake", output)

    with zipfile.ZipFile(output) as archive:
        info = archive.getinfo("bin/trivy")
        assert archive.read(info) == b"\x7fELF fake"
        assert (info.external_attr >> 16) & 0o111


def test_binary_is_taken_from_the_release_archive():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in (("README.md", b"docs"), ("trivy", b"binary")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    assert layer.extract_binary(buffer.getvalue()) == b"binary"


def test_ci_and_terraform_pin_the_same_trivy_as_the_layer():
    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    variables = (
        root / "infra" / "modules" / "step-functions-lambda" / "variables.tf"
    ).read_text(encoding="utf-8")
    assert f"download/v{layer.TRIVY_VERSION}/{layer.TRIVY_ASSET}" in ci
    assert layer.TRIVY_SHA256 in ci
    assert f'default     = "{layer.TRIVY_VERSION}"' in variables
