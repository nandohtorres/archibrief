"""Stage 5: check the model's answer before anyone sees it (ADR-0050 §4).

The model cites by alias; the server resolves each alias against this
review and this turn's retrieved chunks, and keeps only what it can
verify. The rules, all fail-closed:

- A refusal is replaced by a fixed text for its reason; the model's own
  words are discarded.
- A citation survives only if: the finding alias is in this review; a
  chunk quote really appears in that chunk (the review pipeline's tolerant
  matcher, and the stored quote is the source's own span, never the
  model's); a finding-source quote appears in that finding's stored span;
  a resource is in the summary; a requirement is in the baseline answers.
- A paragraph left with no verified citation is dropped. If nothing is
  left, the answer becomes a fixed "not determinable" text. Same policy as
  verify_model_findings: drop individually, never relax.
- Hygiene: URLs and markdown links removed, ref codes in prose replaced
  by the finding's short text, one code block of at most 20 lines, 1,800
  characters in total.
- The per-deploy canary anywhere in the output turns the whole answer into
  a prompt-disclosure refusal, and the caller logs it.

What this doesn't prove: that a real citation supports its sentence. The
UI says "cited answer", never "verified answer".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.chat.context import ReviewContext
from backend.chat.prompt import MISSING_REASONS
from backend.shared.citations import find_quote
from backend.shared.sanitize import clip, remove_invisible

MAX_ANSWER_CHARS = 1800
MAX_PARAGRAPHS = 6
MAX_CODE_LINES = 20
MAX_CODE_CHARS = 1200
MAX_CITATIONS_PER_PARAGRAPH = 6

REFUSAL_TEXTS = {
    "off_topic": "I can only answer questions about this review: its findings, the "
    "evidence behind them, and how to act on them.",
    "code_generation": "I can show a short fix for a specific finding, but not write "
    "whole modules or files. Ask how to fix one finding.",
    "other_data": "I can only see this review. Nothing about other reviews or other "
    "people is available here.",
    "secrets": "I don't read out or handle credentials, keys or passwords, even ones in "
    "the code. Remove them from the code and rotate them.",
    "prompt_disclosure": "I can't share how I'm configured. Ask about a finding instead.",
    "blocked": "That couldn't be processed. Try asking about a specific finding.",
}
NOT_DETERMINABLE_TEXT = "That isn't determinable from this review."
MISSING_TEXTS = {
    "live_aws_state": "It would need the live AWS account's state, which a review of the "
    "code can't see.",
    "traffic_numbers": "It would need real traffic or usage numbers, which weren't given.",
    "data_classification": "It would need to know what data the system holds, which wasn't given.",
    "code_outside_archive": "It would need code that wasn't in the uploaded archive.",
    "not_in_review": "Nothing in the findings or the cited guidance covers it.",
}
PARTIAL_SUFFIX = "The rest isn't determinable from this review."

_FINDING_REF = re.compile(r"^F(\d{1,3})$")
_FINDING_SOURCE_REF = re.compile(r"^C-F(\d{1,3})$")
_CHUNK_REF = re.compile(r"^R(\d{1,2})$")
_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_REF_IN_TEXT = re.compile(r"\b(C-F\d{1,3}|F\d{1,3}|R\d{1,2})\b")
_CODE_BLOCK = re.compile(r"```[^\n`]*\n?(.*?)(?:```|$)", re.DOTALL)


class MalformedAnswer(Exception):
    """The tool input didn't have the answer's shape."""


@dataclass
class VerifiedAnswer:
    status: str
    refusal_reason: str | None
    paragraphs: list[dict[str, Any]]
    citations_total: int = 0
    citations_dropped: int = 0
    canary_hit: bool = False
    cited_text: list[str] = field(default_factory=list)  # for the grounding check


def fixed_answer(status: str, text: str, refusal_reason: str | None = None) -> VerifiedAnswer:
    return VerifiedAnswer(
        status=status,
        refusal_reason=refusal_reason,
        paragraphs=[{"text": text, "citations": []}],
    )


def refusal(reason: str) -> VerifiedAnswer:
    reason = reason if reason in REFUSAL_TEXTS else "off_topic"
    return fixed_answer("refused", REFUSAL_TEXTS[reason], reason)


def _not_determinable(missing: str | None) -> VerifiedAnswer:
    text = NOT_DETERMINABLE_TEXT
    if missing in MISSING_TEXTS:
        text = f"{text} {MISSING_TEXTS[missing]}"
    return fixed_answer("not_determinable", text)


def _resolve(
    citation: Any,
    ctx: ReviewContext,
    chunks: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(citation, dict) or not isinstance(citation.get("ref"), str):
        return None
    ref = citation["ref"].strip()
    quote = citation.get("exact_quote")
    quote = quote if isinstance(quote, str) else ""

    if _FINDING_REF.match(ref) and ref in ctx.finding_ids:
        return {
            "kind": "finding",
            "finding_id": ctx.finding_ids[ref],
            "title": ctx.finding_titles.get(ref, ""),
        }
    if _FINDING_SOURCE_REF.match(ref) and ref in ctx.finding_citations:
        stored = ctx.finding_citations[ref]
        span = find_quote(quote, stored["span"]) if quote.strip() else stored["span"]
        if span is None:
            return None
        return {
            "kind": "source",
            "finding_id": ctx.finding_ids[ref[2:]],
            "quote": span,
            "source_url": stored["source_url"],
            "heading_path": stored["heading_path"],
        }
    if _CHUNK_REF.match(ref) and ref in chunks:
        chunk = chunks[ref]
        span = find_quote(quote, chunk["text"])
        if span is None:
            return None
        return {
            "kind": "source",
            "chunk_id": chunk.get("chunk_id", ""),
            "quote": span,
            "source_url": chunk.get("source_url", ""),
            "heading_path": chunk.get("heading_path", ""),
        }
    if ref.startswith("resource:") and ref[len("resource:") :] in ctx.resource_addresses:
        return {"kind": "resource", "address": ref[len("resource:") :]}
    if ref.startswith("requirement:") and ref[len("requirement:") :] in ctx.requirement_labels:
        name = ref[len("requirement:") :]
        return {"kind": "requirement", "field": name, "label": ctx.requirement_labels[name]}
    return None


def _clean_text(text: str, ctx: ReviewContext, code_budget: list[int]) -> str:
    text = remove_invisible(text)
    text = _MARKDOWN_LINK.sub(lambda m: m.group(1), text)
    text = _URL.sub("", text)

    def ref_name(match: re.Match[str]) -> str:
        ref = match.group(1)
        alias = ref.removeprefix("C-")
        if alias in ctx.finding_titles:
            return f'"{clip(ctx.finding_titles[alias], 60)}"'
        return "the cited guidance"

    def code_block(match: re.Match[str]) -> str:
        if code_budget[0] <= 0:
            return "(code omitted)"
        code_budget[0] -= 1
        lines = match.group(1).rstrip("\n").split("\n")
        body = "\n".join(lines[:MAX_CODE_LINES])
        if len(lines) > MAX_CODE_LINES or len(body) > MAX_CODE_CHARS:
            body = body[:MAX_CODE_CHARS].rstrip() + "\n# (shortened)"
        return f"```\n{body}\n```"

    # Code first, so ref codes and URLs inside a code block are kept as code.
    parts = []
    last = 0
    for match in _CODE_BLOCK.finditer(text):
        prose = text[last : match.start()]
        parts.append(_REF_IN_TEXT.sub(ref_name, prose))
        parts.append(code_block(match))
        last = match.end()
    parts.append(_REF_IN_TEXT.sub(ref_name, text[last:]))
    cleaned = "".join(parts)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def verify_answer(
    raw: Any,
    ctx: ReviewContext,
    chunks: dict[str, dict[str, Any]],
    canary: str,
) -> VerifiedAnswer:
    if not isinstance(raw, dict) or not isinstance(raw.get("paragraphs", []), list):
        raise MalformedAnswer("answer is not an object with a paragraphs list")
    if canary and canary in repr(raw):
        answer = refusal("prompt_disclosure")
        answer.canary_hit = True
        return answer

    status = raw.get("status")
    if status == "refused":
        return refusal(str(raw.get("refusal_reason")))
    if status not in ("answered", "not_determinable"):
        raise MalformedAnswer(f"unknown status {status!r}")
    missing = raw.get("missing") if raw.get("missing") in MISSING_REASONS else None

    total = dropped = 0
    code_budget = [1]
    kept: list[dict[str, Any]] = []
    cited_text: list[str] = []
    for paragraph in raw.get("paragraphs", [])[:MAX_PARAGRAPHS]:
        if not isinstance(paragraph, dict) or not isinstance(paragraph.get("text"), str):
            continue
        citations: list[dict[str, Any]] = []
        for citation in (paragraph.get("citations") or [])[:MAX_CITATIONS_PER_PARAGRAPH]:
            total += 1
            resolved = _resolve(citation, ctx, chunks)
            if resolved is None or resolved in citations:
                dropped += resolved is None
                continue
            citations.append(resolved)
        text = _clean_text(paragraph["text"], ctx, code_budget)
        if not citations or not text:
            continue
        kept.append({"text": text, "citations": citations})
        for c in citations:
            cited_text.append(c.get("quote") or c.get("title") or "")

    if not kept:
        answer = _not_determinable(missing or ("not_in_review" if status == "answered" else None))
        answer.citations_total, answer.citations_dropped = total, dropped
        return answer

    if status == "not_determinable":
        suffix = PARTIAL_SUFFIX
        if missing:
            suffix = f"{suffix} {MISSING_TEXTS[missing]}"
        kept.append({"text": suffix, "citations": []})

    # Cap the whole answer; the last kept paragraph is cut if needed.
    budget = MAX_ANSWER_CHARS
    capped: list[dict[str, Any]] = []
    for paragraph in kept:
        if budget <= 0:
            break
        if len(paragraph["text"]) > budget:
            paragraph = {**paragraph, "text": clip(paragraph["text"], budget)}
        # +1 for the line break between paragraphs when they're shown joined.
        budget -= len(paragraph["text"]) + 1
        capped.append(paragraph)

    return VerifiedAnswer(
        status=status,
        refusal_reason=None,
        paragraphs=capped,
        citations_total=total,
        citations_dropped=dropped,
        cited_text=[t for t in cited_text if t],
    )
