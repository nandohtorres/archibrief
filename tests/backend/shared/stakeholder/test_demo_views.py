import json
import re
import tarfile
from pathlib import PurePosixPath

import pytest

from scripts.build_demo_architectures import DEMOS
from scripts.build_demo_architectures import build as build_architecture
from scripts.build_demo_archives import DEMOS as SOURCES
from scripts.build_demo_stakeholder import PLAIN_LANGUAGE, build


@pytest.mark.parametrize(
    "demo_id", ["breach-pattern", "fec-database", "medicare-platform"]
)
def test_shipped_demo_sidecars_are_current(demo_id):
    # A catalog, assessment or reviewer-text change must be followed by
    # `python scripts/build_demo_stakeholder.py`.
    written = json.loads(PLAIN_LANGUAGE.read_text(encoding="utf-8"))
    shipped = (DEMOS / "stakeholder" / f"{demo_id}.json").read_text(encoding="utf-8")
    assert shipped.splitlines() == build(demo_id, written[demo_id]).splitlines()


@pytest.mark.parametrize(
    "demo_id", ["breach-pattern", "fec-database", "medicare-platform"]
)
def test_demo_sidecars_carry_no_prices(demo_id):
    shipped = json.loads(
        (DEMOS / "stakeholder" / f"{demo_id}.json").read_text(encoding="utf-8")
    )
    assert shipped["version"] == 2
    assert "budget" not in shipped
    for block in shipped["blocks"].values():
        assert not {"fix", "inaction", "verdict", "analogy"} & set(block)
    assert not re.search(r"\$\s?\d|\bUSD\s?\d", json.dumps(shipped))


@pytest.mark.parametrize(
    "demo_id", ["breach-pattern", "fec-database", "medicare-platform"]
)
def test_demo_architecture_matches_its_archive_and_saved_findings(demo_id):
    shipped = json.loads(
        (DEMOS / "architecture" / f"{demo_id}.json").read_text(encoding="utf-8")
    )
    assert shipped == json.loads(build_architecture(demo_id))


@pytest.mark.parametrize(
    "demo_id", ["breach-pattern", "fec-database", "medicare-platform"]
)
def test_demo_archive_carries_its_pinned_source_license_and_safe_paths(demo_id):
    source = SOURCES[demo_id]
    with tarfile.open(DEMOS / f"{demo_id}.tar") as archive:
        assert all(
            not PurePosixPath(m.name).is_absolute()
            and ".." not in PurePosixPath(m.name).parts
            for m in archive.getmembers()
        )
        note = archive.extractfile("SOURCE.md").read().decode("utf-8")
        assert (
            source["commit"] in note
            and source["repo"] in note
            and source["license"] in note
        )
        assert archive.extractfile(f"LICENSE-{source['name']}").read()
        assert any(m.name.endswith(".tf") for m in archive.getmembers())
