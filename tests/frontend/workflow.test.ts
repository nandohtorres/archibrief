import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  confidenceLabel,
  filterAndSortFindings,
  formatFindingId,
} from "../../frontend/lib/workflow";

describe("finding workspace behavior", () => {
  it("filters by presentation priority without changing the evidence ledger", () => {
    const originalOrder = fixtureReport.findings.map(
      ({ record }) => record.finding_id,
    );
    const highRisk = filterAndSortFindings(
      fixtureReport.findings,
      "",
      "high",
      "priority",
    );

    expect(highRisk).toHaveLength(3);
    expect(
      highRisk.every(({ presentation }) => presentation.priority === "high"),
    ).toBe(true);
    expect(
      fixtureReport.findings.map(({ record }) => record.finding_id),
    ).toEqual(originalOrder);
  });

  it("searches the title, category, and typed finding kind", () => {
    expect(
      filterAndSortFindings(fixtureReport.findings, "IAM", "all", "priority"),
    ).toHaveLength(1);
    expect(
      filterAndSortFindings(
        fixtureReport.findings,
        "not-observable",
        "all",
        "priority",
      )[0].record.finding_id,
    ).toBe("finding-006");
  });

  it("supports deterministic confidence and title sorting", () => {
    const byConfidence = filterAndSortFindings(
      fixtureReport.findings,
      "",
      "all",
      "confidence",
    );
    const byTitle = filterAndSortFindings(
      fixtureReport.findings,
      "",
      "all",
      "title",
    );

    expect(byConfidence[0].record.finding_id).toBe("finding-006");
    expect(byTitle[0].record.finding).toBe(
      "Bucket-level S3 public-access protection is not declared",
    );
  });

  it("labels confidence and formats stable finding IDs", () => {
    expect(confidenceLabel(0.9)).toBe("High");
    expect(confidenceLabel(0.7)).toBe("Medium");
    expect(confidenceLabel(0.4)).toBe("Low");
    expect(formatFindingId("finding-7")).toBe("F-007");
  });
});
