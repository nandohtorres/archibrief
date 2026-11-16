import { declarationScopeMessage } from "../../frontend/lib/analysis-quality";
import { buildReportHtml } from "../../frontend/lib/chat";
import { fixtureReport } from "../../frontend/lib/fixtures";
import type { ReviewReport } from "../../frontend/lib/contracts";

const scope: NonNullable<ReviewReport["review_scope"]> = {
  version: "review-scope-public@1",
  known_y: 50,
  x: 47,
  count_complete: false,
  model_outcome: "completed",
  categories: { reviewed: 47, unsupported: 2, zero_copy: 1, other: 0 },
  module_gaps: [
    { address: "module.remote", labels: ["remote module not read"] },
  ],
  gaps_complete: true,
  warnings: [],
};

describe("declaration coverage", () => {
  it("reports known lower bounds and every gap without claiming exhaustive analysis", () => {
    const message = declarationScopeMessage(scope);
    expect(message).toContain("47 of 50 known resource declarations");
    expect(message).toContain("whole-workload total is unknown");
    expect(message).toContain("module.remote: remote module not read");
    expect(message).toContain("2 unsupported");
    expect(message).toContain("does not prove every setting");
  });

  it("keeps missing and uncertain delivery distinct from zero reviewed", () => {
    expect(declarationScopeMessage()).toContain("not recorded");
    const unknown = declarationScopeMessage({
      ...scope,
      x: null,
      model_outcome: "unknown",
    });
    expect(unknown).toContain("reviewed count is unknown");
    expect(unknown).not.toContain("Included 0");
    expect(
      declarationScopeMessage({ ...scope, x: 0, model_outcome: "not_invoked" }),
    ).toContain("No AI answer-generation call was made");
  });

  it("uses the same disclosure and escapes names in the HTML export", () => {
    const html = buildReportHtml(
      { ...fixtureReport, review_scope: scope },
      [],
      "Test",
    );
    expect(html).toContain("47 of 50 known resource declarations");
    const unsafe = {
      ...scope,
      module_gaps: [
        {
          address: "<script>alert(1)</script>",
          labels: ["remote module not read"],
        },
      ],
    };
    const escaped = buildReportHtml(
      { ...fixtureReport, review_scope: unsafe },
      [],
      "Test",
    );
    expect(escaped).not.toContain("<script>alert(1)</script>");
    expect(escaped).toContain("&lt;script&gt;");
  });
});
