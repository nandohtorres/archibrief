"""Presentation facts for the Stakeholder Brief (ADR-0062).

The brief's wording and commitment tiers live in the frontend
(frontend/lib/stakeholder-brief.ts), versioned with the page that shows
them. The backend adds only what the frontend cannot work out on its own:
which concern a rule finding is about, and the resource it names. No
text, prices, effort or severity are produced here, so a report never
carries a monetary estimate and the assessment (backend/shared/
assessment.py) is unaffected.

Title inference only chooses an explanation for reviews saved before rule
findings stored their concern; it never assigns a risk assessment.
"""

from __future__ import annotations

import re
from typing import Any

from backend.shared.models.finding import Finding, FindingType
from backend.shared.stakeholder.catalog import infer_concern

BRIEF_META_VERSION = 2

_QUOTED_NAME = re.compile(r"'([^']{1,80})'")


def brief_meta(finding: Finding) -> dict[str, Any] | None:
    """The `brief` block for a rule finding, or None for any other type."""
    if finding.type != FindingType.DETERMINISTIC_RULE_RESULT:
        return None
    if finding.concern:
        concern, source = finding.concern, "recorded"
    else:
        concern = infer_concern(finding.finding)
        source = "title" if concern else None
    name = _QUOTED_NAME.search(finding.finding)
    return {
        "version": BRIEF_META_VERSION,
        "concern": concern,
        "concern_source": source,
        "subject": name.group(1) if name else None,
    }
