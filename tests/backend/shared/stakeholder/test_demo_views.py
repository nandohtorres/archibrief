import json
import re

import pytest

from scripts.build_demo_architectures import DEMOS
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
