import { fixtureReport } from "../../frontend/lib/fixtures";
import { isReviewReport } from "../../frontend/lib/contracts";
import { reportSourceLabels, reportTitle } from "../../frontend/lib/workflow";

describe("sample review (GET /demo)", () => {
  it("accepts a complete report", () => {
    expect(isReviewReport(fixtureReport)).toBe(true);
  });

  it("rejects error bodies and pending pointers", () => {
    expect(isReviewReport({ error: "review not found" })).toBe(false);
    expect(isReviewReport({ reviewId: "r1", status: "pending" })).toBe(false);
    expect(isReviewReport({ ...fixtureReport, findings: undefined })).toBe(
      false,
    );
    expect(isReviewReport(null)).toBe(false);
  });

  it("titles the report from the repo reference instead of a fixed name", () => {
    expect(reportTitle("github.com/example/payments-api@a91f3c2")).toBe(
      "payments-api architecture review",
    );
    expect(reportTitle("github.com/example/streaming-platform")).toBe(
      "streaming-platform architecture review",
    );
    expect(reportTitle("")).toBe("Architecture review");
  });

  it("labels a sample as hypothetical and never as a fixture", () => {
    expect(reportSourceLabels.sample).toMatch(/hypothetical/i);
    expect(reportSourceLabels.sample).not.toMatch(/fixture/i);
    expect(reportSourceLabels.live).not.toMatch(/fixture/i);
  });
});
