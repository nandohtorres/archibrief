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
  model_limit: "This claim exceeded the number of model findings checked in this pass.",
  duplicate_finding: "This repeats another finding; it is retained separately for traceability.",
  duplicate_finding_id: "Repeated finding identifiers prevented an independent check.",
  verification_failed: "The independent check did not finish.",
  insufficient_evidence: "The independent check could not establish this claim.",
  missing_verdict: "The independent check returned no verdict for this claim.",
  duplicate_verdict: "The independent check returned conflicting repeated verdicts.",
  invalid_verdict: "The independent verdict did not pass its validation checks.",
  malformed_response: "The independent response could not be validated.",
  candidate_limit: "This claim could not be independently checked within the call limit.",
  request_size: "This claim could not be independently checked within the request size limit.",
  citation_integrity: "The supplied citation did not pass the source-integrity check.",
  unattributed_scan: "The scan result could not be attributed to this resource instance.",
  incomplete_batch: "The saved deeper result is incomplete and could not be confirmed.",
  fix_not_applicable:
    "The detection may be right, but its proposed fix did not pass the safety check.",
  parent_unverified: "This saved finding depends on a parent that is not in the verified section.",
  other: "The finding could not be confirmed by the review checks.",
};

// Allowlist again on display/download: no raw action/citation/plain fields survive.
export function publicUnverified(value: unknown): UnverifiedFinding[] {
  if (!Array.isArray(value)) return [];
  return value
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
        disposition: code === "contradicted" ? "disproved" : "unable-to-verify",
        submitted_quote: text("submitted_quote", 2000),
        checks: (Array.isArray(v.checks) ? v.checks : [])
          .filter((c: unknown): c is { name: string; status: "passed" | "failed" | "not-run" } =>
            Boolean(
              c &&
              typeof c === "object" &&
              typeof (c as { name?: unknown }).name === "string" &&
              [
                "format",
                "citation",
                "remediation",
                "verification",
                "attribution",
                "duplicate",
                "limit",
              ].includes((c as { name: string }).name) &&
              ["passed", "failed", "not-run"].includes((c as { status: string }).status),
            ),
          )
          .map((c: { name: string; status: "passed" | "failed" | "not-run" }) => ({
            name: c.name,
            status: c.status,
          })),
        supporting_evidence: publicReferences(v.supporting_evidence),
        contradicting_evidence: publicReferences(v.contradicting_evidence),
      };
    });
}

export const UNVERIFIED_NOTE =
  "These claims may be right, but the review could not confirm them. Check them before acting. They are excluded from findings totals and the Stakeholder Brief; recommendations are withheld.";

function publicReferences(value: unknown): NonNullable<UnverifiedFinding["supporting_evidence"]> {
  if (!Array.isArray(value)) return [];
  return value
    .filter((v) => v && typeof v === "object")
    .map((v) => ({
      id: typeof v.id === "string" ? v.id.slice(0, 160) : "",
      kind: ["fact", "passage", "submitted-quote"].includes(v.kind) ? v.kind : "fact",
      text: typeof v.text === "string" ? fieldWithoutMoney(v.text.slice(0, 2000)).text : "",
      truncated: v.truncated === true || (typeof v.text === "string" && v.text.length > 2000),
    }));
}

export function checkTally(item: UnverifiedFinding): string {
  const checks = item.checks ?? [];
  if (!checks.length) return "Check details were not recorded for this older item.";
  const passed = checks.filter((c) => c.status === "passed").length;
  const pending = checks.filter((c) => c.status === "not-run").length;
  return `${passed} of ${checks.length} checks passed${pending ? ` (${pending} not run)` : ""}`;
}
