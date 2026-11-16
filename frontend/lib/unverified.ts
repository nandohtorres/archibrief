import type { UnverifiedFinding } from "./contracts";
import { codeWithoutMoney, fieldWithoutMoney } from "./money-policy";

const REASONS: Record<string, string> = {
  chunk_not_retrieved: "The cited passage was not in the retrieved guidance.",
  quote_not_in_chunk: "The quotation did not match the retrieved guidance.",
  quote_missing: "The finding did not provide a quotation to check.",
  chunk_missing: "The finding did not identify its source passage.",
  citation_on_uncited_type: "The source reference did not match this finding type.",
  rule_type_from_model: "The model labelled its claim as a deterministic rule result.",
  invalid_type: "The finding failed the format check.",
  invalid_fields: "The finding failed the format check.",
  wrong_fix: "The proposed fix did not address the stated problem.",
  unsupported_remediation: "The proposed fix did not pass the safety and applicability check.",
  remediation_contradiction: "The claim or proposed fix conflicts with the declared configuration.",
  rule_owned_remediation: "The proposed fix conflicts with the rule-owned guidance.",
  contradicted: "The additional check found that the claim contradicted the supplied evidence.",
  other: "The finding could not be confirmed by the review checks.",
};

// Allowlist again on display/download: no raw action/citation/plain fields survive.
export function publicUnverified(value: unknown): UnverifiedFinding[] {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, 24)
    .filter((v) => v && typeof v === "object")
    .map((v) => {
      const text = (key: string, limit: number) =>
        typeof v[key] === "string"
          ? (key === "evidence"
              ? codeWithoutMoney(v[key].slice(0, limit))
              : fieldWithoutMoney(v[key].slice(0, limit))
            ).text
          : "";
      const code =
        typeof v.reason_code === "string" && Object.hasOwn(REASONS, v.reason_code)
          ? v.reason_code
          : "other";
      return {
        finding_id: text("finding_id", 128),
        finding: text("finding", 1200),
        evidence: text("evidence", 1600),
        resource: text("resource", 160),
        category: text("category", 64) || null,
        concern: text("concern", 128) || null,
        reason_code: code,
        reason: REASONS[code],
        recommendation_withheld: true,
      };
    });
}

export const UNVERIFIED_NOTE =
  "These claims may be right, but the review could not confirm them. Check them before acting. They are excluded from findings totals and the Stakeholder Brief; recommendations are withheld.";
