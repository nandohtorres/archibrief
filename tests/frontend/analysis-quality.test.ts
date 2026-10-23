import { qualityMessage } from "../../frontend/lib/analysis-quality";
import { buildReportHtml } from "../../frontend/lib/chat";
import { fixtureReport } from "../../frontend/lib/fixtures";
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
