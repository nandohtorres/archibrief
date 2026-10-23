import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  assessmentFor,
  compareAssessments,
} from "../../frontend/lib/assessment";
import { filterAndSortFindings } from "../../frontend/lib/workflow";
import type { ReportFinding } from "../../frontend/lib/contracts";

const base = fixtureReport.findings[0];
const riskyFact: ReportFinding = {
  ...base,
  record: { ...base.record, type: "fact" },
  presentation: { priority: "confirmed", short_label: "Confirmed" },
  assessment: {
    version: 1,
    severity: "critical",
    action: "needed",
    source: "model",
  },
};

it("does not infer severity from legacy priority, type or confidence", () => {
  expect(assessmentFor(base).severity).toBeNull();
  expect(assessmentFor({ ...riskyFact, assessment: undefined }).action).toBe(
    "unknown",
  );
  expect(assessmentFor(riskyFact).severity).toBe("critical");
});

it("filters and sorts risk independently of facts and rule results", () => {
  expect(compareAssessments(riskyFact, base)).toBeLessThan(0);
  expect(
    filterAndSortFindings([base, riskyFact], "", "critical", "priority"),
  ).toEqual([riskyFact]);
  expect(
    filterAndSortFindings([base, riskyFact], "", "unknown", "priority"),
  ).toEqual([base]);
});

it("keeps evidence gaps unassessed even when supplied an assessment", () => {
  expect(
    assessmentFor({
      ...riskyFact,
      record: { ...riskyFact.record, type: "not-observable" },
    }).action,
  ).toBe("unknown");
});
