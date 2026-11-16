// No-monetary-estimates policy for public narrative (ADR-0062).
//
// Generated text (model findings, chat answers, plain summaries) can carry a
// price: "about $32/month", "USD 1,200", "$40-60 a month". The Stakeholder
// Brief, chat and downloads never publish one. Stored records are never
// changed; this builds what the public sees.
//
// backend/shared/money_policy.py implements the same rules, and both are
// checked against tests/shared/money-policy-cases.json. Change them together.
//
// Three modes:
// - field: a short generated field (title, risk). Each amount becomes
//   "[amount removed]".
// - narrative: chat-style text. A prose sentence that states an amount is
//   dropped rather than filled with placeholders. Inside ``` code fences only
//   amounts that are clearly money are replaced (see code mode).
// - code: evidence and code. A bare `$` + whole number is left alone, since
//   in code it is usually a positional variable (`$1`, `awk '{print $1,$2}'`).
//   Amounts with thousands separators, decimals, a scale (k, million), a rate
//   (/month, per hour), a range, US$, USD or "dollars" are replaced.
// Terraform `${...}` and `$NAME` variables never match.

export const MONEY_POLICY_VERSION = "no-monetary-estimates@2026-11-15";
export const AMOUNT_PLACEHOLDER = "[amount removed]";
export const REMOVED_SENTENCE = "A cost estimate was removed from this answer.";
export const MONEY_NOTE =
  "A cost figure in AI-written or saved text was removed here. ArchiBrief does not publish cost estimates; the stored review is unchanged.";
export const QUOTE_OMITTED_NOTE =
  "The quoted passage states a price, so it isn't shown here. Open the source to read it.";

const NUM = String.raw`(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?`;
const SCALE = String.raw`(?:\s?(?:k|m|bn|million|billion|thousand)\b)`;
const RATE = String.raw`(?:\s?(?:\/|per\s|an?\s)\s?(?:month|mo|year|yr|hour|hr|day|week|request|GB)\b)`;
const RANGE = String.raw`(?:\s?(?:-|–|to\s)\s?(?:US\$|\$)?\s?${NUM}${SCALE}?)`;

const MONEY_SOURCE = [
  String.raw`(?:US\$|\$)\s?${NUM}${SCALE}?${RANGE}?${RATE}?`,
  String.raw`\bUSD\s?${NUM}${SCALE}?${RANGE}?${RATE}?`,
  String.raw`\b${NUM}${SCALE}?\s?(?:USD|dollars?)\b`,
].join("|");

function moneyPattern(): RegExp {
  return new RegExp(MONEY_SOURCE, "gi");
}

const BARE_DOLLAR_INTEGER = /^\$[0-9]+$/;

export interface Cleaned {
  text: string;
  // How many amounts were removed (0: the text is unchanged).
  removed: number;
}

export function hasMoney(text: string): boolean {
  return moneyPattern().test(text);
}

export function fieldWithoutMoney(text: string): Cleaned {
  let removed = 0;
  const cleaned = text.replace(moneyPattern(), () => {
    removed += 1;
    return AMOUNT_PLACEHOLDER;
  });
  return { text: cleaned, removed };
}

export function codeWithoutMoney(text: string): Cleaned {
  let removed = 0;
  const cleaned = text.replace(moneyPattern(), (match) => {
    if (BARE_DOLLAR_INTEGER.test(match)) return match;
    removed += 1;
    return AMOUNT_PLACEHOLDER;
  });
  return { text: cleaned, removed };
}

function countMoney(text: string): number {
  return text.match(moneyPattern())?.length ?? 0;
}

function proseWithoutMoneySentences(text: string): Cleaned {
  let removed = 0;
  const lines: string[] = [];
  for (const line of text.split("\n")) {
    const found = countMoney(line);
    if (found === 0) {
      lines.push(line);
      continue;
    }
    removed += found;
    const kept = line.split(/(?<=[.!?])\s+/).filter((sentence) => countMoney(sentence) === 0);
    if (kept.length > 0) lines.push(kept.join(" "));
  }
  return { text: lines.join("\n"), removed };
}

export function narrativeWithoutMoney(text: string): Cleaned {
  let removed = 0;
  const parts = text.split("```").map((part, index) => {
    const cleaned = index % 2 === 1 ? codeWithoutMoney(part) : proseWithoutMoneySentences(part);
    removed += cleaned.removed;
    return cleaned.text;
  });
  if (removed === 0) return { text, removed };
  const joined = parts.join("```");
  return { text: joined.trim() ? joined : REMOVED_SENTENCE, removed };
}
