import re
import tempfile
from pathlib import Path

import pytest

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import _RULE_CONCERNS, ALL_RULES, run_rules
from backend.shared.stakeholder.catalog import HARMS, RECIPES, infer_concern
from backend.shared.stakeholder.pricing import PRICE_ITEMS
from backend.shared.trivy_checks import TRUSTED_CHECKS
from scripts.build_demo_architectures import DEMOS, _extract_tf

_MONEY = re.compile(r"\$\s?\d")


def test_every_rule_and_trusted_check_concern_has_a_recipe():
    concerns = {_RULE_CONCERNS[rule] for rule in ALL_RULES}
    concerns |= {check.concern for check in TRUSTED_CHECKS.values()}
    assert concerns - set(RECIPES) == set()


def test_recipes_only_name_priced_items_and_known_harms():
    for concern, recipe in RECIPES.items():
        assert recipe.harm in HARMS, concern
        assert recipe.components, concern
        for component in recipe.components:
            assert component.item in PRICE_ITEMS, concern
        low, high = recipe.effort_hours
        assert 0 < low <= high, concern


def test_no_hand_written_text_states_a_price():
    # Prices come from the price table only; a caveat names one as "{item}".
    for concern, recipe in RECIPES.items():
        for text in (recipe.title, recipe.analogy, recipe.what_could_happen, recipe.action):
            assert not _MONEY.search(text), concern
        if recipe.caveat:
            assert not _MONEY.search(recipe.caveat), concern
            for placeholder in re.findall(r"\{(\w+)\}", recipe.caveat):
                assert PRICE_ITEMS[placeholder].monthly, concern


def test_harms_cite_a_source_or_give_a_method():
    for key, harm in HARMS.items():
        cited = harm.source_name and (harm.source_url or "").startswith("https://")
        assert cited or harm.method, key


@pytest.mark.parametrize("check_id", sorted(TRUSTED_CHECKS))
def test_trusted_check_titles_infer_their_concern(check_id):
    check = TRUSTED_CHECKS[check_id]
    assert infer_concern(check.title.format(name="services/a_b")) == check.concern


_TRAPS = Path(__file__).resolve().parents[2] / "traps" / "fixtures"
_FIXTURES = Path(__file__).parent / "fixtures"
_SOURCES = [
    "fixture:every_rule",
    *(f"demo:{d}" for d in ("breach-pattern", "fec-database", "medicare-platform")),
    *(f"trap:{d.name}" for d in sorted(_TRAPS.iterdir()) if d.is_dir()),
]


def _parsed(source: str) -> dict:
    kind, name = source.split(":")
    if kind == "fixture":
        return vars(parse_terraform_files([str(_FIXTURES / f"{name}.tf")]))
    if kind == "trap":
        return vars(parse_terraform_files([str(p) for p in sorted((_TRAPS / name).glob("*.tf"))]))
    with tempfile.TemporaryDirectory() as scratch:
        return vars(parse_terraform_files(_extract_tf(DEMOS / f"{name}.tar", Path(scratch))))


@pytest.mark.parametrize("source", _SOURCES)
def test_rule_titles_infer_the_concern_the_rule_sets(source):
    # Older saved reports have no concern, so the title has to give it back.
    for finding in run_rules(_parsed(source), "r1"):
        if finding.type.value == "not-observable":
            assert finding.concern is None
            assert finding.citation is None
            assert finding.evidence
            continue
        assert finding.concern in RECIPES
        assert infer_concern(finding.finding) == finding.concern, finding.finding


def test_every_python_rule_is_covered_by_a_source():
    fired = {f.concern for source in _SOURCES for f in run_rules(_parsed(source), "r1")}
    assert {_RULE_CONCERNS[rule] for rule in ALL_RULES} - fired == set()


def test_unknown_titles_have_no_concern():
    assert infer_concern("The proxy is a single EC2 instance") is None
