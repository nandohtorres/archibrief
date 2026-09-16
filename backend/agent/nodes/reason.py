"""LangGraph node: Reason.

Runs inside the AgentCore Runtime + LangGraph subworkflow (ADR-0028), NOT
as a standalone Lambda.

Synthesizes RuleEngine output + retrieved evidence into typed `Finding`
objects via Bedrock Claude. Lightweight-first-pass prose by default
(ADR-0023), but every required field is still populated per ADR-0039.
Persists model ID, prompt version, corpus version, and retrieved chunk
IDs as a snapshot (ADR-0039), so a later "go deeper" is a versioned
child, not a disconnected re-run.

Prompt construction uses ADR-0022's structured system/user-content
separation — the workload brief and retrieved evidence are passed as
distinct, clearly-delimited fields, never concatenated into one string
with instructions.

Note on Classify (ADR-0033): no separate Classify node. Guardrails runs
inline at Ingest and again here before calling the model.
"""

from __future__ import annotations

import itertools
import json
import re
import uuid

from pydantic import ValidationError

from backend.shared.clients import BedrockReasoningClient, GuardrailsClient, ToolCallMissing
from backend.shared.models.finding import (
    AlternativeConsidered,
    Citation,
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
)

# Bumped 2026-09-16: the model-facing contract changed materially (tool-use
# forcing + chunk_id/exact_quote instead of an asked-for Citation object),
# so a finding persisted under the old free-text-citation prompt is not
# reproducible under this prompt_version — see ADR-0039.
PROMPT_VERSION = "reason_prompt@2026-09-16"

_TOOL_NAME = "emit_findings"

SYSTEM_PROMPT = """You are ArchiBrief's evidence-grounded reasoning stage.
The rule_engine_findings you're given are already-finalized results from a
separate deterministic rule engine — do not restate, summarize, or emit any
of them yourself. Your job is to synthesize the retrieved AWS
Well-Architected Framework evidence into NEW findings (fact, inference,
assumption, recommendation, or not-observable) that go beyond what the
rule engine already established, and call the emit_findings tool with your
results — never answer in plain text. You must:
- Never emit a finding of type "deterministic-rule-result" — that type is
  reserved for the rule engine's own output, which application code
  attaches separately. Application code will reject any finding of this
  type coming from you.
- For any finding type other than "not-observable", set chunk_id to the
  exact chunk_id of one retrieved evidence chunk that supports the claim,
  and set exact_quote to text copied VERBATIM (same characters, same
  casing/punctuation) from that chunk's "text" field — never paraphrase
  the quote. Application code will reject any finding whose chunk_id or
  quote can't be verified against the retrieved evidence you were given.
- Use "not-observable" ONLY when the workload brief gives you no
  information to assess a specific practice AND you have no framework
  text to cite about that specific gap — in that exact case, set
  chunk_id and exact_quote to null; that type carries no citation. If you
  have found a supporting WAF chunk (e.g. guidance describing a relevant
  capability, control, or recommendation), that is NOT a not-observable
  finding even if the brief doesn't confirm whether the workload already
  does it — classify it as "recommendation" or "fact" instead, with that
  chunk as its citation. In short: if you have a citation, never call it
  not-observable.
- Never label a design "compliant" — describe framework alignment, not
  certification.
- Populate every field in the schema, even in lightweight mode.
- Tag any finding that depends on an assumed default as type "assumption"."""


class GuardrailBlocked(Exception):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"Guardrails blocked content at stage: {stage}")


class FindingValidationError(Exception):
    """One or more model-returned findings failed server-side validation —
    citation verification (unknown chunk_id, unsupported quote), a
    forbidden type (deterministic-rule-result), or a malformed shape
    (bad confidence_inputs, alternatives_considered, etc.) — raised with
    every failure listed together so the caller sees the full picture in
    one shot, not one crash at a time. Renamed from CitationVerificationError
    2026-09-16 once its scope grew to cover shape validation too, per
    Codex review (a shape error used to raise immediately and silently
    discard any citation failures already collected for other items in
    the same batch)."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        super().__init__("finding validation failed:\n" + "\n".join(failures))


# The model must never emit this type itself — see SYSTEM_PROMPT and
# _resolve_citation's explicit rejection below. Closes a real grounding
# bypass Codex flagged 2026-09-16: deterministic-rule-result findings
# carry no citation by design, so a model that could freely choose this
# type could self-label ANY invented, ungrounded claim with it to skip
# citation verification entirely. Excluding it from the schema's `type`
# enum is a soft (prompt-level, not server-enforced-by-itself) defense;
# _resolve_citation's explicit rejection of it on any model-returned item
# is the real enforcement.
_MODEL_ALLOWED_TYPES = [t.value for t in FindingType if t != FindingType.DETERMINISTIC_RULE_RESULT]
_CITATIONLESS_TYPES = {FindingType.NOT_OBSERVABLE}

# Builds a regex that tolerates whitespace-run and unicode-punctuation-
# variant drift between the model's re-typed quote and the corpus's raw
# extracted text, then searches the ORIGINAL (non-normalized) chunk text
# and keeps the real matched substring — not the model's version — as
# exact_text_span. Two real, independent reasons this matters, not one:
# (1) this corpus's PDF-derived chunks have documented whitespace/
# boilerplate quirks (see the 2026-09-14/15 PDF-parsing entries in
# Work-Project-Issues-Log.md) and Claude commonly "cleans up" punctuation/
# whitespace when copying a quote, so a byte-exact match would reject
# genuinely correct citations; (2) Citation.exact_text_span is meant to be
# independently reproducible against the real corpus (ADR-0027/ADR-0036) —
# storing the model's possibly-altered version instead of the source's
# actual characters would silently break that reproducibility guarantee
# (Codex review 2026-09-16).
_PUNCTUATION_NORMALIZE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)
_PUNCTUATION_VARIANT_CLASSES = {
    "'": "['‘’]",
    '"': '["“”]',
    "-": "[-–—]",
}

# A PDF line-wrap can hyphenate a word right at the page's right margin
# ("identity-\nbased"), but the model naturally re-types it as one unbroken
# word ("identity-based"). Tolerate optional whitespace immediately after a
# hyphen so a source-side line wrap doesn't break the match.
_HYPHEN_VARIANT_CLASS = _PUNCTUATION_VARIANT_CLASSES["-"] + r"\s*"

# PDF extraction can inject a running header/footer block mid-sentence at a
# page boundary, e.g. "...and \nREL13-BP03 Test disaster recovery
# implementation to validate the implementation 249\n\nReliability Pillar
# AWS Well-Architected Framework\nthe primary fails...". The model correctly
# quotes the flowing sentence and skips this boilerplate, so tolerate an
# optional occurrence of it wherever the quote has a plain word gap. This is
# a fixed, recognizable structure (a "<ID>-BP<n> <title> <page#>" line
# followed by a "<Pillar Name> AWS Well-Architected Framework" line) — not
# an arbitrary "skip any text" hole, so it can't be used to paper over a
# real quote mismatch.
_PAGE_BREAK_BOILERPLATE = (
    r"(?:[A-Z0-9][A-Z0-9.]*-BP\d+[^\n]{0,200}?\d+\s*\n+[^\n]{0,80}AWS Well-Architected Framework\s*)?"
)


_LIGATURE_ASCII_TO_CHAR = {
    "ffi": "ﬃ",
    "ffl": "ﬄ",
    "ff": "ﬀ",
    "fi": "ﬁ",
    "fl": "ﬂ",
}
_LIGATURE_KEYS_BY_LENGTH = sorted(_LIGATURE_ASCII_TO_CHAR, key=len, reverse=True)


def _escape_with_ligature_tolerance(text: str) -> str:
    # PDF extraction leaves Unicode ligature glyphs (e.g. U+FB01 "fi") in the
    # source chunk text, but the model naturally writes the plain ASCII
    # expansion when quoting it. Match either form at the source side.
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        for key in _LIGATURE_KEYS_BY_LENGTH:
            if text.startswith(key, i):
                ligature_char = _LIGATURE_ASCII_TO_CHAR[key]
                parts.append(f"(?:{re.escape(key)}|{re.escape(ligature_char)})")
                i += len(key)
                break
        else:
            ch = text[i]
            if ch == "-":
                parts.append(_HYPHEN_VARIANT_CLASS)
            else:
                parts.append(_PUNCTUATION_VARIANT_CLASSES.get(ch, re.escape(ch)))
            i += 1
    return "".join(parts)


def _build_tolerant_pattern(quote: str) -> re.Pattern[str]:
    normalized = quote.translate(_PUNCTUATION_NORMALIZE_MAP)
    parts: list[str] = []
    for is_space, group in itertools.groupby(normalized, key=str.isspace):
        text = "".join(group)
        if is_space:
            parts.append(r"\s+" + _PAGE_BREAK_BOILERPLATE)
        else:
            parts.append(_escape_with_ligature_tolerance(text))
    return re.compile("".join(parts))

_FINDING_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": [c.value for c in FindingCategory]},
                    "type": {"type": "string", "enum": _MODEL_ALLOWED_TYPES},
                    "finding": {"type": "string"},
                    "evidence": {"type": "string"},
                    "chunk_id": {
                        "type": ["string", "null"],
                        "description": (
                            "chunk_id of the ONE retrieved evidence chunk that supports this "
                            "finding, or null for deterministic-rule-result/not-observable."
                        ),
                    },
                    "exact_quote": {
                        "type": ["string", "null"],
                        "description": (
                            "Verbatim substring copied from that chunk's text field, or null "
                            "for deterministic-rule-result/not-observable."
                        ),
                    },
                    # No minimum/maximum here — confirmed live 2026-09-16
                    # (real ValidationException, first attempt with
                    # strict:true): "For 'number' type, properties
                    # maximum, minimum are not supported" under Bedrock's
                    # strict tool schema enforcement. Pydantic's own
                    # Field(ge=0.0, le=1.0) on Finding.confidence and
                    # ConfidenceInputs (backend/shared/models/finding.py)
                    # still enforces the same bounds server-side — no
                    # actual validation is lost by removing them here.
                    "confidence": {"type": "number"},
                    "confidence_inputs": {
                        "type": "object",
                        "properties": {
                            "evidence_directness": {"type": "number"},
                            "source_agreement": {"type": "number"},
                            "rule_determinism": {"type": "number"},
                        },
                        "required": ["evidence_directness", "source_agreement", "rule_determinism"],
                        "additionalProperties": False,
                    },
                    "risk_impact": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "framework_mapping": {"type": "array", "items": {"type": "string"}},
                    "alternatives_considered": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "reason_rejected": {"type": "string"},
                            },
                            "required": ["option", "reason_rejected"],
                            "additionalProperties": False,
                        },
                    },
                    "depth_level": {"type": "string", "enum": ["lightweight", "deep"]},
                },
                "required": [
                    "category",
                    "type",
                    "finding",
                    "evidence",
                    "chunk_id",
                    "exact_quote",
                    "confidence",
                    "confidence_inputs",
                    "risk_impact",
                    "recommendation",
                    "framework_mapping",
                    "alternatives_considered",
                    "depth_level",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def build_user_content(
    workload_brief: str,
    rule_findings: list[dict],
    retrieved_chunks: list[dict],
) -> dict:
    return {
        "workload_brief": workload_brief,
        "rule_engine_findings": rule_findings,
        "retrieved_evidence": retrieved_chunks,
    }


def call_reasoning_model(
    reasoning_client: BedrockReasoningClient,
    workload_brief: str,
    rule_findings: list[dict],
    retrieved_chunks: list[dict],
    max_tokens: int,
) -> list[dict]:
    user_content = json.dumps(build_user_content(workload_brief, rule_findings, retrieved_chunks))
    tool_input = reasoning_client.converse_structured(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        max_tokens=max_tokens,
        tool_name=_TOOL_NAME,
        tool_description="Emit the synthesized findings for this review.",
        input_schema=_FINDING_INPUT_SCHEMA,
    )
    # A known failure mode seen in the wild with forced Bedrock tool use is
    # toolUse.input coming back as an empty dict ({}) instead of the real
    # arguments (e.g. aws/aws-sdk-go-v2#3048) — fail with a message that
    # names the actual problem instead of a bare KeyError on "findings".
    # Also require "findings" to actually be a list (Codex review
    # 2026-09-16: the old check accepted null or a dict here too, which
    # would have crashed confusingly, or in the empty-list case succeeded
    # silently with zero findings and no signal anything was off).
    findings = tool_input.get("findings") if isinstance(tool_input, dict) else None
    if not isinstance(findings, list):
        raise ToolCallMissing(
            f"{_TOOL_NAME!r} tool call returned no usable 'findings' list: {tool_input!r}"
        )
    return findings


def _resolve_citation(
    item: dict,
    index: int,
    chunk_by_id: dict[str, dict],
    corpus_version: str,
    failures: list[str],
) -> Citation | None:
    finding_type = item["type"]
    chunk_id = item.get("chunk_id")
    exact_quote = item.get("exact_quote")

    if finding_type == FindingType.DETERMINISTIC_RULE_RESULT.value:
        failures.append(
            f"finding[{index}]: model emitted type 'deterministic-rule-result', which is "
            f"reserved for the rule engine's own output and must not come from the model"
        )
        return None

    if finding_type in {t.value for t in _CITATIONLESS_TYPES}:
        if chunk_id is not None or exact_quote is not None:
            failures.append(
                f"finding[{index}]: type {finding_type!r} must not carry a chunk_id/exact_quote "
                f"(got chunk_id={chunk_id!r}, exact_quote={exact_quote!r})"
            )
        return None

    if not chunk_id:
        failures.append(f"finding[{index}]: type {finding_type!r} requires a chunk_id but got none")
        return None
    chunk = chunk_by_id.get(chunk_id)
    if chunk is None:
        failures.append(f"finding[{index}]: chunk_id {chunk_id!r} is not in the retrieved evidence set")
        return None

    # Reject non-string and whitespace-only quotes explicitly. Without
    # this, a whitespace-only quote (e.g. "   ") is truthy so it passes
    # the `not exact_quote` guard below, but its tolerant pattern would
    # match zero-or-more whitespace at the very start of any chunk text —
    # a real bug found by Codex review 2026-09-16, verified reproducible
    # before this fix.
    if not isinstance(exact_quote, str) or not exact_quote.strip():
        failures.append(
            f"finding[{index}]: type {finding_type!r} requires a non-empty string exact_quote, "
            f"got {exact_quote!r}"
        )
        return None

    match = _build_tolerant_pattern(exact_quote).search(chunk["text"])
    if match is None:
        failures.append(
            f"finding[{index}]: exact_quote does not appear (even after whitespace/punctuation "
            f"tolerance) in chunk {chunk_id!r} (quote={exact_quote!r})"
        )
        return None

    return Citation(
        source_url=chunk["source_url"],
        source_edition=chunk.get("source_edition"),
        retrieved_at=chunk["retrieved_at"],
        document_id=chunk["document_id"],
        chunk_id=chunk_id,
        content_hash=chunk["content_hash"],
        heading_path=chunk["heading_path"],
        # The real matched substring from the source chunk, not the
        # model's (possibly whitespace/punctuation-drifted) quote — keeps
        # exact_text_span independently reproducible against the actual
        # corpus per ADR-0027/ADR-0036 (Codex review 2026-09-16).
        exact_text_span=match.group(0),
        parser_version=chunk["parser_version"],
        corpus_version=chunk.get("corpus_version", corpus_version),
    )


def parse_model_findings(
    raw_findings: list[dict],
    review_id: str,
    model_id: str,
    corpus_version: str,
    retrieved_chunks: list[dict],
    deterministic_rule_version: str | None,
) -> list[Finding]:
    """Builds real, server-verified Finding objects from the model's
    chunk_id/exact_quote pairs — the model never supplies a Citation
    directly (per Codex review 2026-09-16: a model-supplied citation string
    can't be trusted to actually be in the evidence it was given, and the
    old free-text citation raised a ValidationError on every real run
    anyway, since Citation is a structured object).

    Every item in the batch is checked — citation verification AND Finding
    shape/type validation — before anything is raised. The original version
    of this function let a shape error (e.g. a malformed confidence_inputs
    or an unexpected alternatives_considered key) raise immediately out of
    Finding(...)/AlternativeConsidered(...), which aborted the whole batch
    and silently discarded every citation failure already collected for
    OTHER items — so a single malformed finding could hide real grounding
    problems the caller genuinely needed to see (Codex review 2026-09-16,
    reproduced directly before this fix: a batch with one bad citation and
    one malformed confidence_inputs raised a bare pydantic ValidationError
    with no mention of the citation problem at all)."""
    if not isinstance(raw_findings, list):
        raise ToolCallMissing(f"expected a list of findings, got {raw_findings!r}")

    chunk_by_id = {c["chunk_id"]: c for c in retrieved_chunks}
    retrieved_chunk_ids = [c.get("chunk_id", "") for c in retrieved_chunks]

    failures: list[str] = []
    findings: list[Finding] = []
    for index, item in enumerate(raw_findings):
        if not isinstance(item, dict):
            failures.append(f"finding[{index}]: expected an object, got {item!r}")
            continue

        failures_before = len(failures)
        citation = _resolve_citation(item, index, chunk_by_id, corpus_version, failures)
        if len(failures) != failures_before:
            # this item failed citation verification — already recorded
            # above; skip building a Finding from it but keep checking the
            # rest of the batch
            continue

        try:
            findings.append(
                Finding(
                    finding_id=str(uuid.uuid4()),
                    review_id=review_id,
                    category=FindingCategory(item["category"]),
                    type=FindingType(item["type"]),
                    finding=item["finding"],
                    evidence=item["evidence"],
                    citation=citation,
                    confidence=item["confidence"],
                    confidence_inputs=ConfidenceInputs(**item["confidence_inputs"]),
                    risk_impact=item["risk_impact"],
                    recommendation=item["recommendation"],
                    framework_mapping=item["framework_mapping"],
                    alternatives_considered=[
                        AlternativeConsidered(**a) for a in item.get("alternatives_considered", [])
                    ],
                    depth_level=item.get("depth_level", "lightweight"),
                    model_id=model_id,
                    prompt_version=PROMPT_VERSION,
                    corpus_version=corpus_version,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    deterministic_rule_version=deterministic_rule_version,
                )
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            failures.append(f"finding[{index}]: failed to build a valid Finding: {exc}")

    if failures:
        raise FindingValidationError(failures)
    return findings


def resolve_rule_findings(rule_findings: list[dict]) -> list[Finding]:
    """Validates the rule engine's own already-finalized Finding dicts
    (backend/lambdas/rule_engine/handler.py builds real Finding objects
    directly, not raw dicts the model needs to reconstruct) and returns
    them as real Finding instances — this is the server-side counterpart
    to the model no longer being allowed to emit
    type="deterministic-rule-result" itself (see SYSTEM_PROMPT and
    _resolve_citation). reason_node merges this with parse_model_findings'
    output for the final reasoned_findings state."""
    failures: list[str] = []
    findings: list[Finding] = []
    for index, item in enumerate(rule_findings):
        try:
            findings.append(Finding.model_validate(item))
        except ValidationError as exc:
            failures.append(f"rule_finding[{index}]: failed to validate as a Finding: {exc}")
    if failures:
        raise FindingValidationError(failures)
    return findings


def reason_node(state: dict) -> dict:
    guardrails: GuardrailsClient = state["guardrails_client"]
    reasoning_client: BedrockReasoningClient = state["reasoning_client"]

    workload_brief = state["workload_brief"]
    if not guardrails.check(workload_brief, source="INPUT"):
        raise GuardrailBlocked("reason_input")

    retrieved_chunks = state.get("retrieved_chunks", [])
    rule_findings = state.get("rule_findings", [])

    raw_findings = call_reasoning_model(
        reasoning_client=reasoning_client,
        workload_brief=workload_brief,
        rule_findings=rule_findings,
        retrieved_chunks=retrieved_chunks,
        max_tokens=state.get("max_tokens", 4096),
    )

    model_findings = parse_model_findings(
        raw_findings=raw_findings,
        review_id=state["review_id"],
        model_id=reasoning_client.model_id,
        corpus_version=state.get("corpus_version", "unknown"),
        retrieved_chunks=retrieved_chunks,
        deterministic_rule_version=state.get("deterministic_rule_version"),
    )
    findings = resolve_rule_findings(rule_findings) + model_findings

    return {
        **state,
        "reasoned_findings": [f.model_dump(mode="json") for f in findings],
    }
