"""Estimated chat cost, for the global daily cap and the log (ADR-0050 §5).

Estimates, not billing. Anthropic list prices in $ per million tokens
(input, 5-minute cache write, cache read, output), times 1.10 for the US
cross-region inference profiles: Anthropic states regional endpoints
cost 10% more than global from Sonnet 4.5 / Haiku 4.5 on, and a
third-party listing of Bedrock's Sonnet 4.6 US price agreed. Confirm the
real Bedrock rates before fixing the caps (master-list item 29).

A $ per million tokens is the same number of micro-dollars per token,
which is why the arithmetic below has no scale factor.
"""

from __future__ import annotations

REGIONAL_MARKUP = 1.10

# (input, cache write, cache read, output) $/M tokens, matched by substring.
_PRICES: list[tuple[str, tuple[float, float, float, float]]] = [
    ("claude-haiku-4-5", (1.00, 1.25, 0.10, 5.00)),
    ("claude-sonnet-4-6", (3.00, 3.75, 0.30, 15.00)),
    ("claude-sonnet-5", (2.00, 2.50, 0.20, 10.00)),
]
# Unknown models are priced as the most expensive listed one, so a model
# switch can't make the cap more generous by accident.
_FALLBACK = max((p for _, p in _PRICES), key=lambda p: p[3])

# Bedrock Guardrails: $0.15 per 1,000 text units for content filters and
# for denied topics (each policy is billed), $0.10 per 1,000 for the
# contextual grounding check; one text unit is up to 1,000 characters.
GUARDRAIL_INPUT_MICRO_USD_PER_UNIT = 300  # prompt-attack filter + denied topics
GROUNDING_MICRO_USD_PER_UNIT = 100
CHARS_PER_TOKEN_WORST_CASE = 3


def _prices(model_id: str) -> tuple[float, float, float, float]:
    for name, prices in _PRICES:
        if name in model_id:
            return prices
    return _FALLBACK


def text_units(chars: int) -> int:
    return max(1, -(-chars // 1000))


def model_cost_micro_usd(model_id: str, usage: dict[str, int]) -> int:
    input_price, write_price, read_price, output_price = _prices(model_id)
    cost = (
        usage.get("inputTokens", 0) * input_price
        + usage.get("cacheWriteInputTokens", 0) * write_price
        + usage.get("cacheReadInputTokens", 0) * read_price
        + usage.get("outputTokens", 0) * output_price
    )
    return round(cost * REGIONAL_MARKUP)


def reserve_micro_usd(model_id: str, prompt_chars: int, max_output_tokens: int) -> int:
    """Worst case for one question: every prompt token billed at the cache
    write price, at a pessimistic 3 characters per token, plus the full
    output budget and both guardrail checks."""
    _, write_price, _, output_price = _prices(model_id)
    prompt_tokens = -(-prompt_chars // CHARS_PER_TOKEN_WORST_CASE)
    model = (prompt_tokens * write_price + max_output_tokens * output_price) * REGIONAL_MARKUP
    guardrails = GUARDRAIL_INPUT_MICRO_USD_PER_UNIT + GROUNDING_MICRO_USD_PER_UNIT * 8
    return round(model) + guardrails
