"""The `Finding` pydantic model — single schema for the typed evidence ledger.

See Work-Project-Coding-Conventions.md ("Typed-finding discipline") and
ADR-0002, ADR-0027, ADR-0036, ADR-0039.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


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
    source_edition: str
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
