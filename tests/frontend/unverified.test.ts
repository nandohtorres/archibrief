import { fixtureReport } from "../../frontend/lib/fixtures";
import { publicUnverified, checkTally } from "../../frontend/lib/unverified";
import { buildReportExport } from "../../frontend/lib/report-review";
import { buildReportHtml } from "../../frontend/lib/chat";
import { buildBrief } from "../../frontend/lib/stakeholder-brief";
import { publicTurn } from "../../frontend/lib/public-projection";
import type { ChatTurn, ReviewReport } from "../../frontend/lib/contracts";

const rejected = {
  finding_id: "unverified-test",
  finding: "Rejected claim aws_db_instance.test",
  evidence: "Unconfirmed ${var.setting}",
  resource: "aws_db_instance.test",
  category: "iam",
  concern: null,
  reason_code: "wrong_fix",
  reason: "untrusted reason",
  recommendation_withheld: true as const,
  recommendation: "WITHHELD_FIX",
  plain: { action: "WITHHELD_FIX" },
  citation: { exact_text_span: "WITHHELD_FIX" },
};
const report: ReviewReport = {
  ...fixtureReport,
  unverified_findings: [rejected],
};

it("preserves disproved evidence and accurate tallies in both exports without actions", () => {
  const disproved = publicUnverified([
    {
      ...rejected,
      reason_code: "contradicted",
      checks: [
        { name: "format", status: "passed" },
        { name: "verification", status: "failed" },
        { name: "remediation", status: "not-run" },
      ],
      supporting_evidence: [
        { id: "c1", kind: "passage", text: "Supporting quote" },
      ],
      contradicting_evidence: [
        {
          id: "resource:a",
          kind: "fact",
          text: "<script>unsafe()</script> enabled=true $500/month",
        },
      ],
    },
  ]);
  const value: ReviewReport = {
    ...fixtureReport,
    disproved_findings: disproved,
  };
  const exported = buildReportExport(value, []);
  expect(exported.disproved_findings).toHaveLength(1);
  expect(buildBrief(value)).toEqual(buildBrief(fixtureReport));
  expect(checkTally(disproved[0])).toBe("1 of 3 checks passed (1 not run)");
  const html = buildReportHtml(value, [], "synthetic");
  expect(html).toContain("Disproved");
  expect(html).toContain("Supporting quote");
  expect(html).toContain("enabled=true");
  expect(html).toContain("1 of 3 checks passed (1 not run)");
  expect(html).not.toContain("<script>unsafe()");
  expect(html).not.toContain("WITHHELD_FIX");
  expect(html).not.toContain("$500");
  expect(JSON.stringify(exported)).not.toContain("WITHHELD_FIX");
});

it("separates failed claims from counted and brief findings", () => {
  expect(buildBrief(report)).toEqual(buildBrief(fixtureReport));
  const exported = buildReportExport(report, []);
  expect(exported.findings).toHaveLength(fixtureReport.findings.length);
  expect(exported.unverified_findings).toHaveLength(1);
  expect(JSON.stringify(exported)).not.toContain("WITHHELD_FIX");
  expect(exported.unverified_findings[0].reason).not.toBe("untrusted reason");
});

it("both downloads preserve the unverified claim but never a withheld action or citation", () => {
  const html = buildReportHtml(report, [], "synthetic");
  expect(html).toContain("Unable to verify");
  expect(html).toContain("Rejected claim");
  expect(html).toContain("Recommendation withheld");
  expect(html).not.toContain("WITHHELD_FIX");
  expect(html).not.toContain("untrusted reason");
});

it("bounds untrusted records and removes prices while preserving Terraform references", () => {
  const items = publicUnverified(
    Array(100).fill({ ...rejected, finding: "$500/month " + "x".repeat(5000) }),
  );
  expect(items).toHaveLength(100);
  expect(items[0].finding.length).toBeLessThanOrEqual(1220);
  expect(items[0].finding).not.toContain("$500");
  expect(items[0].evidence).toContain("${var.setting}");
  expect(publicUnverified([null, false, 42])).toEqual([]);
});

it("labels AI failure in the downloaded report even with no rejected records", () => {
  const failed: ReviewReport = {
    ...fixtureReport,
    analysis_quality: {
      version: 1,
      outcome: "rules-only",
      model_verification: null,
      schema_validation: null,
      reason_codes: ["model_unavailable"],
    },
  };
  expect(buildReportHtml(failed, [], "synthetic")).toContain(
    "The AI analysis failed or timed out",
  );
});

it("keeps unsupported chat notes labelled and cleaned in both downloads", () => {
  const turn: ChatTurn = {
    question_id: "synthetic",
    kind: "custom",
    suggested_id: null,
    question: "Why?",
    status: "answered",
    refusal_reason: null,
    answer: [{ text: "Cited answer", citations: [] }],
    unsupported: ["Unsupported text with $600/month."],
    asked_at: null,
    model_id: null,
    prompt_version: null,
  };
  const cleaned = publicTurn(turn).turn;
  expect(cleaned.unsupported?.join(" ")).not.toContain("$600");
  expect(cleaned.answer[0].text).toBe("Cited answer");
  const html = buildReportHtml(fixtureReport, [turn], "synthetic");
  expect(html).toContain("<strong>Unsupported</strong>");
  expect(html).not.toContain("$600");
  expect(
    JSON.stringify(buildReportExport(fixtureReport, [turn])),
  ).not.toContain("$600");
});
