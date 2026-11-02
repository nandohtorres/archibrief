"""Terraform observations in the shorter form the reasoning model reads.

Kept apart from terraform_observations.py, which builds the full bundles:
that module needs the HCL parser, and the AgentCore runtime package leaves
the parser out (it's ingestion-only). The runtime importing it failed
every review's model step on 2026-11-02; tests/backend/agent/
test_runtime_imports.py now guards that.
"""

from __future__ import annotations

# The model reads observations in this shorter form. The full bundle above,
# with fact IDs and the resource name on every fact, stays server-side for
# the report, the diagram and the configuration checks; repeating it to the
# model made observations three quarters of a review's resource summary
# (2026-10-29). Nothing is dropped except that repetition: every state and
# every basis other than the plain declared configuration is kept.
MODEL_FORMAT_NOTE = (
    "Each resource's observations: facts maps a setting to its known value, "
    "or to {value, basis} when the value comes from something other than "
    "the declared configuration; absent lists settings inspected and not "
    "set; unknown and unsupported map a setting to why it couldn't be "
    "resolved; refs maps a setting to the submitted resource it references; "
    "coverage lists only the domains that were inspected, so any domain not "
    "listed was not inspected. provider.account is unknown for every "
    "resource: the runtime identity is never observed."
)


def _by_setting(pairs: list[tuple[str, object]]) -> dict:
    """Setting to value, or to a list of values for a setting seen twice."""
    grouped: dict[str, list] = {}
    for setting, value in pairs:
        grouped.setdefault(setting, []).append(value)
    return {
        setting: values[0] if len(values) == 1 else values for setting, values in grouped.items()
    }


def compact_for_model(bundle: dict) -> dict:
    """One resource's observations in the model's shorter form."""
    facts: list[tuple[str, object]] = []
    absent: list[str] = []
    unknown: list[tuple[str, object]] = []
    unsupported: list[tuple[str, object]] = []
    for fact in bundle.get("facts", []):
        setting, state, basis = fact.get("setting"), fact.get("state"), fact.get("basis")
        if (setting, state, basis) == (
            "provider.account",
            "unknown",
            "runtime_identity_not_observed",
        ):
            continue
        if state == "known":
            value = fact.get("value")
            facts.append(
                (
                    setting,
                    value
                    if basis == "declared_configuration"
                    else {"value": value, "basis": basis},
                )
            )
        elif state == "absent":
            absent.append(setting)
        elif state == "unsupported":
            unsupported.append((setting, basis))
        else:
            unknown.append((setting, basis))
    refs: list[tuple[str, object]] = []
    for relation in bundle.get("relations", []):
        setting, state = relation.get("setting"), relation.get("state")
        if state == "known":
            refs.append((setting, relation.get("target")))
        elif state == "absent":
            absent.append(setting)
        else:
            unknown.append((setting, relation.get("basis")))
    compact: dict = {}
    for key, value in (
        ("facts", _by_setting(facts)),
        ("absent", absent),
        ("unknown", _by_setting(unknown)),
        ("unsupported", _by_setting(unsupported)),
        ("refs", _by_setting(refs)),
        (
            "coverage",
            {
                domain: level
                for domain, level in (bundle.get("coverage") or {}).items()
                if level != "not_inspected"
            },
        ),
    ):
        if value:
            compact[key] = value
    if bundle.get("creation") not in (None, "declared"):
        compact["creation"] = bundle["creation"]
    module = (bundle.get("source") or {}).get("module")
    if module not in (None, "root"):
        compact["module"] = module
    for flag in ("omitted_items", "truncated", "incomplete"):
        if bundle.get(flag):
            compact[flag] = bundle[flag]
    return compact
