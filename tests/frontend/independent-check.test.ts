import {
  qualityMessage,
  independentCheckLabel,
} from "../../frontend/lib/analysis-quality";
import { buildReportHtml } from "../../frontend/lib/chat";
import { buildReportExport } from "../../frontend/lib/report-review";
import { fixtureReport } from "../../frontend/lib/fixtures";
import type { ReviewReport } from "../../frontend/lib/contracts";

test("incomplete checks disclose retention, never claim unverified findings were dropped", () => {
  const message = qualityMessage({
    version: 1,
    outcome: "complete",
    model_verification: null,
    schema_validation: null,
    reason_codes: ["additional_verification_incomplete"],
  });
  expect(message).toContain("retained");
  expect(message).not.toContain("left out");
});

test("per-finding check labels survive HTML and JSON exports", () => {
  const finding = {
    ...fixtureReport.findings[0],
    independent_check: "not-independently-checked" as const,
  };
  const report: ReviewReport = { ...fixtureReport, findings: [finding] };
  expect(independentCheckLabel(finding)).toBe("Not independently checked");
  expect(buildReportHtml(report, [], "Synthetic review")).toContain(
    "Not independently checked",
  );
  expect(buildReportExport(report, []).findings[0].independent_check).toBe(
    "not-independently-checked",
  );
});

test("unsafe fix label does not erase a retained detection", () => {
  const finding = {
    ...fixtureReport.findings[0],
    independent_check: "fix-needs-confirmation" as const,
  };
  expect(independentCheckLabel(finding)).toContain("Detection retained");
});
