"""The `Finding` pydantic model — single schema for the typed evidence ledger.

See ADR-0002, ADR-0027, ADR-0036 and ADR-0039.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.shared.stakeholder.catalog import HARMS
from backend.shared.stakeholder.pricing import PRICE_ITEM_KEYS


class FindingType(str, Enum):
    FACT = "fact"
    DETERMINISTIC_RULE_RESULT = "deterministic-rule-result"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"
    RECOMMENDATION = "recommendation"
    NOT_OBSERVABLE = "not-observable"


class FindingCategory(str, Enum):
    IAM = "iam"
    EXPOSURE = "exposure"
    ENCRYPTION = "encryption"
    AVAILABILITY = "availability"
    RECOVERY = "recovery"
    OBSERVABILITY = "observability"
    COST = "cost"


class DepthLevel(str, Enum):
    LIGHTWEIGHT = "lightweight"
    DEEP = "deep"


class Citation(BaseModel):
    source_url: str
    # Optional to match the corpus Chunk model (backend/corpus/models.py):
    # some sources, such as HTML pages, have no dated edition.
    source_edition: str | None
    retrieved_at: datetime
    canonical_url: str | None = None
    document_id: str
    chunk_id: str | None = None
    content_hash: str
    heading_path: str
    exact_text_span: str
    parser_version: str
    corpus_version: str


class ConfidenceInputs(BaseModel):
    evidence_directness: float = Field(ge=0.0, le=1.0)
    source_agreement: float = Field(ge=0.0, le=1.0)
    rule_determinism: float = Field(ge=0.0, le=1.0)


class AlternativeConsidered(BaseModel):
    option: str
    reason_rejected: str


class FixComponent(BaseModel):
    """One thing a fix adds, named from the price table. Code prices it
    (backend/shared/stakeholder/pricing.py); no dollar amount is stored."""

    item: str
    quantity: int = Field(default=1, ge=1, le=20)
    size: str | None = Field(default=None, max_length=32)

    @field_validator("item")
    @classmethod
    def _known_item(cls, item: str) -> str:
        if item not in PRICE_ITEM_KEYS:
            raise ValueError(f"unknown price item {item!r}")
        return item


class PlainLanguage(BaseModel):
    """A finding explained for a non-engineer, for the stakeholder view.

    Rule findings get theirs from backend/shared/stakeholder/catalog.py;
    this is for findings the model writes ("model") and for demo findings
    explained by hand ("reviewer")."""

    written_by: Literal["model", "reviewer"]
    title: str = Field(min_length=1, max_length=160)
    analogy: str = Field(max_length=400)
    what_could_happen: str = Field(max_length=400)
    action: str = Field(max_length=400)
    # False for a finding that only confirms something is already right.
    needs_action: bool
    severity: Literal["critical", "high", "medium", "low"]
    # A backend/shared/stakeholder/catalog.py HARMS key, or None.
    harm: str | None = None
    fix_components: list[FixComponent] = Field(default_factory=list, max_length=6)
    effort_hours_low: float = Field(ge=0, le=400)
    effort_hours_high: float = Field(ge=0, le=400)

    @field_validator("harm")
    @classmethod
    def _known_harm(cls, harm: str | None) -> str | None:
        if harm is not None and harm not in HARMS:
            raise ValueError(f"unknown harm {harm!r}")
        return harm

    @model_validator(mode="after")
    def _effort_range(self) -> PlainLanguage:
        if self.effort_hours_high < self.effort_hours_low:
            raise ValueError("effort_hours_high is below effort_hours_low")
        return self


class Finding(BaseModel):
    finding_id: str
    review_id: str
    category: FindingCategory
    type: FindingType
    finding: str
    evidence: str
    citation: Citation | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_inputs: ConfidenceInputs
    risk_impact: str
    recommendation: str
    framework_mapping: list[str]
    alternatives_considered: list[AlternativeConsidered] = Field(default_factory=list)
    depth_level: DepthLevel

    model_id: str | None = None
    prompt_version: str | None = None
    corpus_version: str | None = None
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    deterministic_rule_version: str | None = None
    parent_finding_id: str | None = None
    # What a rule finding is about (e.g. "rds_multi_az"), set by the rule
    # engine; the stakeholder view's catalog is keyed by it.
    concern: str | None = None
    plain: PlainLanguage | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _check_citation_matches_type(self) -> Finding:
        if self.type == FindingType.NOT_OBSERVABLE and self.citation is not None:
            raise ValueError("a not-observable finding cannot carry a citation")
        if (
            self.type not in (FindingType.NOT_OBSERVABLE, FindingType.DETERMINISTIC_RULE_RESULT)
            and self.citation is None
        ):
            raise ValueError(f"finding of type {self.type} requires a citation")
        return self
