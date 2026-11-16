// What the public sees of stored review text (ADR-0062).
//
// Applies the no-monetary-estimates policy (money-policy.ts) field by field.
// The stored record is never changed: these return copies, and say what was
// changed so a download is never presented as the unchanged raw record.
//
// - Generated narrative fields: amounts replaced (field mode).
// - Evidence: code mode, so `${...}`, `$NAME` and `$1` stay as written.
// - Exact quotes (citation spans, chat source quotes): never edited. A quote
//   that states a price is omitted and marked, keeping its source link.
// - IDs, severity, assessments, citation anchors and counters: untouched.
// - Plain-block estimate fields (effort hours, priced fix components, loss
//   harm key) are left out of the public copy.

import type { ChatParagraph, ChatTurn, Finding } from "./contracts";
import {
  MONEY_POLICY_VERSION,
  codeWithoutMoney,
  fieldWithoutMoney,
  hasMoney,
  narrativeWithoutMoney,
} from "./money-policy";

export interface PublicParagraph extends ChatParagraph {
  amounts_removed?: number;
}

export function publicParagraph(paragraph: ChatParagraph): {
  paragraph: PublicParagraph;
  removed: number;
  omitted: number;
} {
  const cleaned = narrativeWithoutMoney(paragraph.text);
  let omitted = 0;
  const citations = paragraph.citations.map((citation) => {
    if (citation.kind === "source" && citation.quote && hasMoney(citation.quote)) {
      omitted += 1;
      return { ...citation, quote: "", quote_omitted: "monetary-amount" as const };
    }
    return citation;
  });
  // A current backend already cleaned the text and counted what it removed.
  const earlier = (paragraph as PublicParagraph).amounts_removed ?? 0;
  const removed = cleaned.removed + earlier;
  return {
    paragraph: {
      ...paragraph,
      text: cleaned.text,
      citations,
      ...(removed ? { amounts_removed: removed } : {}),
    },
    removed: cleaned.removed,
    omitted,
  };
}

export function publicTurn(turn: ChatTurn): { turn: ChatTurn; removed: number; omitted: number } {
  let removed = 0;
  let omitted = 0;
  const answer = turn.answer.map((p) => {
    const cleaned = publicParagraph(p);
    removed += cleaned.removed;
    omitted += cleaned.omitted;
    return cleaned.paragraph;
  });
  return { turn: { ...turn, answer }, removed, omitted };
}

const NARRATIVE_FIELDS = ["finding", "risk_impact", "recommendation"] as const;
const PLAIN_TEXT_FIELDS = ["title", "analogy", "what_could_happen", "action"] as const;
const PLAIN_ESTIMATE_FIELDS = ["fix_components", "effort_hours_low", "effort_hours_high", "harm"];

export function publicRecord(record: Finding): { record: Finding; changed: string[] } {
  const changed: string[] = [];
  const copy: Finding = { ...record };
  for (const field of NARRATIVE_FIELDS) {
    const cleaned = fieldWithoutMoney(record[field]);
    if (cleaned.removed) {
      copy[field] = cleaned.text;
      changed.push(field);
    }
  }
  const evidence = codeWithoutMoney(record.evidence);
  if (evidence.removed) {
    copy.evidence = evidence.text;
    changed.push("evidence");
  }
  if (record.alternatives_considered?.length) {
    copy.alternatives_considered = record.alternatives_considered.map((alt, index) => {
      const option = fieldWithoutMoney(alt.option);
      const reason = fieldWithoutMoney(alt.reason_rejected);
      if (option.removed + reason.removed) changed.push(`alternatives_considered[${index}]`);
      return { option: option.text, reason_rejected: reason.text };
    });
  }
  if (record.citation && hasMoney(record.citation.exact_text_span)) {
    copy.citation = { ...record.citation, exact_text_span: "" };
    changed.push("citation.exact_text_span (omitted)");
  }
  const plain = record.plain;
  if (plain && typeof plain === "object" && !Array.isArray(plain)) {
    const source = plain as Record<string, unknown>;
    const kept: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(source)) {
      if (PLAIN_ESTIMATE_FIELDS.includes(key)) {
        changed.push(`plain.${key} (omitted)`);
        continue;
      }
      if ((PLAIN_TEXT_FIELDS as readonly string[]).includes(key) && typeof value === "string") {
        const cleaned = fieldWithoutMoney(value);
        if (cleaned.removed) changed.push(`plain.${key}`);
        kept[key] = cleaned.text;
        continue;
      }
      kept[key] = value;
    }
    copy.plain = kept;
  }
  return { record: copy, changed };
}

export const PUBLIC_POLICY_NOTE =
  "Public copy. Cost figures in generated text were removed and estimate fields left out under ArchiBrief's no-cost-estimates policy; changed fields are listed per finding. Exact quotes are never edited: a quote that states a price is omitted. The stored review is unchanged.";

export { MONEY_POLICY_VERSION };
