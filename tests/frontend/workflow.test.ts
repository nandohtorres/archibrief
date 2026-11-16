import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  REVIEW_DEADLINE_MS,
  citationGap,
  confidenceLabel,
  defaultReportName,
  failureMessageFor,
  filterAndSortFindings,
  formatFindingId,
} from "../../frontend/lib/workflow";

describe("finding workspace behavior", () => {
  it("keeps legacy unassessed findings distinct without changing the evidence ledger", () => {
    const originalOrder = fixtureReport.findings.map(
      ({ record }) => record.finding_id,
    );
    const highRisk = filterAndSortFindings(
      fixtureReport.findings,
      "",
      "unknown",
      "priority",
    );

    expect(highRisk).toHaveLength(fixtureReport.findings.length);
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

describe("citationGap", () => {
  it("calls only a not-observable finding an evidence gap", () => {
    expect(citationGap("not-observable").heading).toBe("No citation by design");
    expect(citationGap("deterministic-rule-result").heading).toBe(
      "Configuration evidence, not a citation",
    );
    expect(citationGap("deterministic-rule-result").body).toContain(
      "read the submitted configuration directly",
    );
    expect(citationGap("inference").heading).toBe("No source citation");
  });
});

describe("failureMessageFor", () => {
  it("explains pilot rejection and distinguishes lower-bound counts", () => {
    const exact = failureMessageFor("resource_limit_exceeded", {
      known_y: 84,
      count_complete: true,
    });
    const partial = failureMessageFor("resource_limit_exceeded", {
      known_y: 84,
      count_complete: false,
    });
    expect(exact).toContain("84 resource declarations");
    expect(partial).toContain("84 known resource declarations");
    expect(partial).toContain("total may be larger");
    expect(exact).toContain("No paid AI analysis was started");
    expect(failureMessageFor("scope_manifest_required")).toContain(
      "archive root",
    );
    expect(
      failureMessageFor("resource_limit_exceeded", {
        known_y: NaN,
        count_complete: true,
      }),
    ).toBe(failureMessageFor("resource_limit_exceeded"));
  });
  it.each([
    "invalid_archive",
    "input_blocked",
    "paused",
    "timed_out",
    "clarification_expired",
    "clarification_limit",
    "clarification_retired",
    "cancelled",
  ])("gives a specific message for %s", (code) => {
    expect(failureMessageFor(code)).not.toBe(failureMessageFor(undefined));
  });

  it("falls back to a generic message for unknown codes", () => {
    expect(failureMessageFor("internal_error")).toBe(
      failureMessageFor(undefined),
    );
    expect(failureMessageFor("Lambda.Unknown")).toMatch(/Something went wrong/);
  });

  it("allows longer than the slowest backend stage before giving up", () => {
    expect(REVIEW_DEADLINE_MS).toBeGreaterThan(300_000);
  });
});

describe("defaultReportName", () => {
  it("names a blank report after the uploaded archive", () => {
    const file = (name: string) => new File(["x"], name);
    expect(defaultReportName("upload", file("payments-api.tar.gz"))).toBe(
      "payments-api",
    );
    expect(defaultReportName("upload", file("infra.TGZ"))).toBe("infra");
    expect(defaultReportName("upload", file("main.tar"))).toBe("main");
  });

  it("falls back for pasted Terraform and for no file at all", () => {
    expect(defaultReportName("paste", null)).toBe("Pasted Terraform");
    expect(defaultReportName("upload", null)).toBe("Untitled review");
    expect(defaultReportName("upload", new File(["x"], ".tar"))).toBe(
      "Untitled review",
    );
  });
});
