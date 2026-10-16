"""Stages 1 and 2 of ADR-0046's injection defense: normalize, then bound.

Every untrusted string the chat handles passes through here before it can
reach a prompt: the visitor's question, and every string taken from the
stored report (which the review model wrote from untrusted input).

Stage 1, normalize:
- Unicode NFKC, so fullwidth and other compatibility forms ("ｉｇｎｏｒｅ")
  become the plain letters a filter expects.
- Zero-width, bidi-control, tag-block and other invisible characters are
  removed, so hidden text and "ig\\u200bnore" splits can't slip past a
  later check.
- Runs of spaces collapse to one; at most one blank line is kept.

Questions get two more checks, as rejections rather than rewrites:
- a word mixing Latin with Cyrillic or Greek letters (lookalike spelling
  NFKC doesn't fold, e.g. Cyrillic "і" in "іgnore");
- a base64-looking run of 40+ characters that decodes to readable text
  (an encoded instruction).

Stage 2, bound: hard length caps, applied after normalizing so the cap
counts what the model would really see.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata

MAX_QUESTION_CHARS = 500

# Removed outright: every format character (Unicode category Cf: zero-width
# space/joiners, bidi controls, soft hyphen, BOM, and the U+E0000 "tag"
# block used to smuggle invisible ASCII), private-use and unassigned code
# points, the combining grapheme joiner, and variation selectors (which can
# also carry hidden bytes).
_REMOVED_CATEGORIES = {"Cf", "Co", "Cn", "Cs"}
_INVISIBLE = re.compile("[\u034f\ufe00-\ufe0f\U000e0100-\U000e01ef]")
_SPACES = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n(\s*\n)+")
_WORD = re.compile(r"\w+")
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


class QuestionRejected(Exception):
    """The question can't be accepted. `reason` is a short fixed code,
    never text from the question."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def remove_invisible(value: str) -> str:
    """Only the invisible-character removal, keeping spacing and line
    starts as they are. Used on model output, where a code block's
    indentation matters."""
    text = _INVISIBLE.sub("", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Control characters (C0 except tab and newline, DEL, C1) and the
    # categories above.
    return "".join(
        ch
        for ch in text
        if ch in "\n\t"
        or (
            unicodedata.category(ch) != "Cc" and unicodedata.category(ch) not in _REMOVED_CATEGORIES
        )
    )


def normalize_text(value: str) -> str:
    """Stage 1. Idempotent: normalize_text(normalize_text(x)) == normalize_text(x)."""
    text = remove_invisible(unicodedata.normalize("NFKC", value))
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def clip(value: str, limit: int) -> str:
    """Stage 2 for report text: cut to `limit` characters, marking the cut."""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(script):
            return script
    return "OTHER"


def _mixes_scripts(text: str) -> bool:
    for word in _WORD.findall(text):
        scripts = {s for s in map(_script, word) if s in ("LATIN", "CYRILLIC", "GREEK")}
        if "LATIN" in scripts and len(scripts) > 1:
            return True
    return False


def _has_encoded_text(text: str) -> bool:
    for run in _BASE64_RUN.findall(text):
        padded = run + "=" * (-len(run) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if not decoded:
            continue
        printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in decoded)
        if printable / len(decoded) > 0.9:
            return True
    return False


def check_question(raw: object) -> str:
    """Stages 1-2 for a visitor's question: the normalized text, or
    QuestionRejected. A rejection never uses one of the review's questions."""
    if not isinstance(raw, str):
        raise QuestionRejected("not_text")
    text = normalize_text(raw)
    if not text:
        raise QuestionRejected("empty")
    if len(text) > MAX_QUESTION_CHARS:
        raise QuestionRejected("too_long")
    if _mixes_scripts(text):
        raise QuestionRejected("mixed_scripts")
    if _has_encoded_text(text):
        raise QuestionRejected("encoded_text")
    return text
