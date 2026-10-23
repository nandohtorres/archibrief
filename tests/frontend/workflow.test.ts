import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  REVIEW_DEADLINE_MS,
  citationGap,
  confidenceLabel,
  defaultReportName,
  failureMessageFor,
  filterAndSortFindings,
  formatFindingId,
  stakeholderSummary,
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
  it.each([
    "invalid_archive",
    "input_blocked",
    "paused",
    "timed_out",
    "clarification_expired",
    "clarification_limit",
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

describe("stakeholder summary", () => {
  const finding = (
    priority: "high" | "review" | "confirmed" | "unknown",
    title: string,
  ) => ({
    ...fixtureReport.findings[0],
    record: {
      ...fixtureReport.findings[0].record,
      finding_id: title,
      finding: title,
    },
    presentation: { priority, short_label: priority },
  });

  it("names the submitted workload instead of the sample's", () => {
    const summary = stakeholderSummary({
      ...fixtureReport,
      terraform_repo_ref: "github.com/acme/billing-service@abc123",
    });
    expect(summary.heading).toBe("What this review means for billing-service");
    expect(summary.heading).not.toContain("payments-api");
  });

  it("counts real findings and starts with the high-risk ones", () => {
    const summary = stakeholderSummary({
      ...fixtureReport,
      findings: [
        finding("high", "Database is public"),
        finding("high", "Storage is not encrypted"),
        finding("review", "Consider IAM auth"),
        finding("confirmed", "Multi-AZ enabled"),
      ],
    });
    expect(summary.intro).toMatch(/^2 high-risk configuration gaps were found/);
    expect(summary.intro).toContain("plus 1 item to review");
    expect(summary.startWith).toEqual([
      "Database is public",
      "Storage is not encrypted",
    ]);
  });

  it("says plainly when there is nothing high-risk", () => {
    const summary = stakeholderSummary({ ...fixtureReport, findings: [] });
    expect(summary.intro).toBe(
      "No high-risk configuration gaps were found by the deterministic checks.",
    );
    expect(summary.startWith).toEqual([]);
  });

  it("lists workload answers that weren't supplied", () => {
    const summary = stakeholderSummary({
      ...fixtureReport,
      baseline_answers: [
        {
          field: "a",
          label: "Traffic",
          outcome: "answered",
          value: "low",
          policy_version: "1",
        },
        {
          field: "b",
          label: "Data residency",
          outcome: "not-observable",
          value: "",
          policy_version: "1",
        },
        {
          field: "c",
          label: "Availability",
          outcome: "assumption",
          value: "std",
          policy_version: "1",
        },
      ],
    });
    expect(summary.coverageLimits).toEqual([
      "Data residency was not supplied, so conclusions that depend on it are not observable.",
      "Availability was not supplied, so a conservative assumption was used.",
    ]);
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
