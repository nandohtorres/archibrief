import {
  qualityMessage,
  scopeMessage,
} from "../../frontend/lib/analysis-quality";
import { buildReportHtml } from "../../frontend/lib/chat";
import { fixtureReport } from "../../frontend/lib/fixtures";
import { buildReportExport } from "../../frontend/lib/report-review";
import type { AnalysisQuality } from "../../frontend/lib/contracts";

it("qualifies an empty report whose proposed findings were all rejected", () => {
  const quality: AnalysisQuality = {
    version: 1,
    outcome: "all-rejected",
    model_verification: { attempted: 2, accepted: 0, rejected: 2 },
    schema_validation: { attempted: 0, accepted: 0, rejected: 0 },
    reason_codes: ["model_verification_rejected"],
  };
  const report = { ...fixtureReport, findings: [], analysis_quality: quality };
  expect(qualityMessage(quality)).toContain(
    "An empty report is not a clean review",
  );
  expect(buildReportHtml(report, [], "Review")).toContain(
    qualityMessage(quality),
  );
  expect(qualityMessage()).toContain("counts were not recorded");
});

it("keeps configuration coverage limits in HTML and JSON exports", () => {
  const analysis_scope = {
    version: "terraform-observations@2026-10-23" as const,
    facts_emitted: 30,
    omitted_resources: 2,
    omitted_items: 1,
    incomplete_resources: 1,
    truncated: true,
    runtime_verified: false as const,
  };
  const report = { ...fixtureReport, analysis_scope };
  expect(buildReportExport(report, []).analysis_scope).toEqual(analysis_scope);
  expect(scopeMessage(analysis_scope)).toContain(
    "missing details do not establish absence",
  );
  expect(scopeMessage(analysis_scope)).toContain(
    "Some expressions could not be checked",
  );
  expect(buildReportHtml(report, [], "Review")).toContain(
    scopeMessage(analysis_scope),
  );
});
