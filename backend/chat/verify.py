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
import unicodedata
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
# Any scheme link (http, ftp, javascript:, data:, mailto: ...), www.
# hosts, and dotted-host obfuscations like evil[.]com. Plain dotted names
# such as aws_s3_bucket.logs are kept: they're resource addresses.
_URL = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]{1,15}://\S*|\b(?:javascript|data|vbscript|mailto|file):\S*"
    r"|\bwww\.\S+|\S*\[\.\]\S*|\S*\(dot\)\S*)",
    re.IGNORECASE,
)
# A code block may show a fix, never fetch and run something (security
# review 2026-10-15): lines that download or pipe into a shell are dropped.
_FETCH_OR_EXEC = re.compile(
    r"\b(?:curl|wget|iwr|Invoke-WebRequest|Invoke-Expression|iex|certutil|bitsadmin)\b"
    r"|\|\s*(?:ba|z|k)?sh\b|\|\s*python\d*\b|\bbase64\s+-d",
    re.IGNORECASE,
)
# A quote shorter than this proves nothing (one letter matches any chunk).
MIN_QUOTE_CHARS = 20
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


def _squash(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", remove_invisible(text)).casefold().split())


def _leaks(canary: str, text: str) -> bool:
    """The canary in the text, ignoring case, spacing, invisible and
    compatibility characters."""
    return bool(canary) and _squash(canary) in _squash(text)


def _canary_refusal() -> VerifiedAnswer:
    answer = refusal("prompt_disclosure")
    answer.canary_hit = True
    return answer


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
        if quote.strip() and len(quote.strip()) < min(MIN_QUOTE_CHARS, len(stored["span"])):
            return None
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
        if len(quote.strip()) < min(MIN_QUOTE_CHARS, len(chunk["text"].strip())):
            return None
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


def _clean_prose(text: str, ctx: ReviewContext, chunk_refs: set[str]) -> str:
    text = _MARKDOWN_LINK.sub(lambda m: m.group(1), text)
    text = _URL.sub("", text)

    def ref_name(match: re.Match[str]) -> str:
        ref = match.group(1)
        alias = ref.removeprefix("C-")
        if alias in ctx.finding_titles:
            return f'"{clip(ctx.finding_titles[alias], 60)}"'
        if ref in chunk_refs:
            return "the cited guidance"
        return ref  # not one of ours (e.g. "R53"): leave it alone

    text = _REF_IN_TEXT.sub(ref_name, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _clean_code(body: str, code_budget: list[int]) -> str:
    if code_budget[0] <= 0:
        return "(code omitted)"
    code_budget[0] -= 1
    lines = [
        line
        for line in body.rstrip("\n").split("\n")
        if not _FETCH_OR_EXEC.search(line) and not _URL.search(line)
    ]
    if not any(line.strip() for line in lines):
        return "(code omitted)"
    kept = "\n".join(lines[:MAX_CODE_LINES])
    if len(lines) > MAX_CODE_LINES or len(kept) > MAX_CODE_CHARS:
        kept = kept[:MAX_CODE_CHARS].rstrip() + "\n# (shortened)"
    return f"```\n{kept}\n```"


def _clean_text(text: str, ctx: ReviewContext, code_budget: list[int], chunk_refs: set[str]) -> str:
    """Split out code blocks first, so link stripping and ref rewriting
    only touch prose and a code block's own characters and indentation are
    kept (code review 2026-10-15). Code only loses fetch/exec and URL lines."""
    text = remove_invisible(text)
    parts = []
    last = 0
    for match in _CODE_BLOCK.finditer(text):
        parts.append(_clean_prose(text[last : match.start()], ctx, chunk_refs))
        parts.append(_clean_code(match.group(1), code_budget))
        last = match.end()
    parts.append(_clean_prose(text[last:], ctx, chunk_refs))
    return re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()


def _clip_paragraph(text: str, limit: int) -> str:
    """clip(), without leaving a code fence open: a block that doesn't fit
    is dropped rather than cut in half."""
    clipped = clip(text, limit)
    if clipped.count("```") % 2 == 1:
        clipped = clip(clipped[: clipped.rindex("```")].rstrip() or "…", limit)
    return clipped


def verify_answer(
    raw: Any,
    ctx: ReviewContext,
    chunks: dict[str, dict[str, Any]],
    canary: str,
) -> VerifiedAnswer:
    if not isinstance(raw, dict) or not isinstance(raw.get("paragraphs", []), list):
        raise MalformedAnswer("answer is not an object with a paragraphs list")
    if _leaks(canary, repr(raw)):
        return _canary_refusal()

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
        text = _clean_text(paragraph["text"], ctx, code_budget, set(chunks))
        if not citations or not text:
            continue
        kept.append({"text": text, "citations": citations})
        for c in citations:
            cited_text.append(c.get("quote") or c.get("title") or "")

    # Checked again on the cleaned text: cleaning removes invisible
    # characters, which could have hidden a split-up canary from the raw
    # check (security review 2026-10-15).
    if _leaks(canary, " ".join(p["text"] for p in kept)):
        return _canary_refusal()

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
            paragraph = {**paragraph, "text": _clip_paragraph(paragraph["text"], budget)}
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
