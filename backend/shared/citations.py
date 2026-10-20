"""Tolerant quote matching for citations, shared by reviews and chat.

Moved out of backend/agent/nodes/reason.py (2026-10-15, ADR-0050) so the
chat Lambda verifies a quoted span exactly the way the review pipeline
does, without importing the agent package. Behaviour is unchanged.
"""

from __future__ import annotations

import itertools
import re

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
_PAGE_BREAK_BOILERPLATE = r"(?:[A-Z0-9][A-Z0-9.]*-BP\d+[^\n]{0,200}?\d+\s*\n+[^\n]{0,80}AWS Well-Architected Framework\s*)?"


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


def build_tolerant_pattern(quote: str) -> re.Pattern[str]:
    normalized = quote.translate(_PUNCTUATION_NORMALIZE_MAP)
    parts: list[str] = []
    for is_space, group in itertools.groupby(normalized, key=str.isspace):
        text = "".join(group)
        if is_space:
            parts.append(r"\s+" + _PAGE_BREAK_BOILERPLATE)
        else:
            parts.append(_escape_with_ligature_tolerance(text))
    return re.compile("".join(parts))


def find_quote(quote: object, text: str) -> str | None:
    """The source's own matched span for `quote` in `text`, or None.

    Non-string and whitespace-only quotes never match: a whitespace-only
    quote's pattern would match at the start of any text (Codex review
    2026-09-16).
    """
    if not isinstance(quote, str) or not quote.strip():
        return None
    match = build_tolerant_pattern(quote).search(text)
    return match.group(0) if match else None
