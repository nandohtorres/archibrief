import json

import pytest

from scripts.build_demo_architectures import DEMOS
from scripts.build_demo_stakeholder import PLAIN_LANGUAGE, build


@pytest.mark.parametrize("demo_id", ["breach-pattern", "fec-database", "medicare-platform"])
def test_shipped_demo_views_match_the_price_table_and_catalog(demo_id):
    # A price or catalog change must be followed by
    # `python scripts/build_demo_stakeholder.py`.
    written = json.loads(PLAIN_LANGUAGE.read_text(encoding="utf-8"))
    shipped = (DEMOS / "stakeholder" / f"{demo_id}.json").read_text(encoding="utf-8")
    assert shipped.splitlines() == build(demo_id, written[demo_id]).splitlines()
