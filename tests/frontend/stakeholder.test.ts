import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  isStakeholderView,
  withStakeholderView,
  type BudgetSummary,
  type ReviewReport,
  type StakeholderView,
} from "../../frontend/lib/contracts";
import { buildReportHtml } from "../../frontend/lib/chat";
import {
  budgetHeadline,
  formatDollars,
  formatMonthly,
  orderByBudget,
  stakeholderSummary,
} from "../../frontend/lib/workflow";

const DEMOS = join(__dirname, "../../frontend/public/demos");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(join(DEMOS, path), "utf-8"));
}

const DEMO_IDS = ["breach-pattern", "fec-database", "medicare-platform"];

function budget(overrides: Partial<BudgetSummary> = {}): BudgetSummary {
  return {
    item_count: 3,
    free_count: 2,
    monthly_known: 7.59,
    monthly_recommended: 7.59,
    recommended_has_unpriced: false,
    monthly_optional: 0,
    unpriced_items: [],
    effort_hours_low: 1,
    effort_hours_high: 4,
    effort_label: "1 to 4 hours",
    verdict_counts: {
      "fix-today": 2,
      "quick-win": 0,
      "worth-the-money": 1,
      "when-budget-allows": 0,
    },
    rows: [],
    prices_as_of: "2026-10",
    price_region: "us-east-1",
    note: "",
    ...overrides,
  };
}

describe("stakeholder view: money formatting", () => {
  it("shows cents only where they matter", () => {
    expect(formatDollars(0)).toBe("$0");
    expect(formatDollars(7.59)).toBe("$7.59");
    expect(formatDollars(3000)).toBe("$3,000");
  });

  it("marks costs that depend on usage", () => {
    expect(formatMonthly(0, false)).toBe("$0");
    expect(formatMonthly(0, true)).toBe("Usage-based");
    expect(formatMonthly(22.27, true)).toBe("$22.27 + usage");
  });

  it("answers what it will cost in one sentence", () => {
    expect(budgetHeadline(budget())).toBe(
      "3 items need attention: 2 cost nothing to fix, the rest change the AWS bill.",
    );
    expect(budgetHeadline(budget({ free_count: 3 }))).toBe(
      "3 items need attention, and every fix is free on the AWS bill.",
    );
    expect(budgetHeadline(budget({ item_count: 0, free_count: 0 }))).toBe(
      "Nothing here needs fixing.",
    );
  });
});

describe("stakeholder view: demo files", () => {
  it.each(DEMO_IDS)("%s ships a valid view for its own saved report", (id) => {
    const view = readJson(`stakeholder/${id}.json`);
    const report = readJson(`reports/${id}.json`) as ReviewReport;
    expect(isStakeholderView(view)).toBe(true);
    const typed = view as StakeholderView;
    expect(typed.review_id).toBe(report.review_id);
    const ids = new Set(report.findings.map((f) => f.record.finding_id));
    for (const findingId of Object.keys(typed.blocks))
      expect(ids.has(findingId)).toBe(true);
    for (const row of typed.budget.rows)
      expect(typed.blocks[row.finding_id]).toBeDefined();
  });

  it("puts the cards and budget onto the report without changing its findings", () => {
    const report = readJson("reports/breach-pattern.json") as ReviewReport;
    const view = readJson("stakeholder/breach-pattern.json") as StakeholderView;
    const merged = withStakeholderView(report, view);
    expect(merged.budget).toEqual(view.budget);
    expect(merged.findings.map((f) => f.record)).toEqual(
      report.findings.map((f) => f.record),
    );
    expect(merged.findings.every((f) => f.stakeholder !== undefined)).toBe(
      true,
    );
  });

  it("orders findings like the budget table, cards without a row last", () => {
    const report = readJson("reports/breach-pattern.json") as ReviewReport;
    const view = readJson("stakeholder/breach-pattern.json") as StakeholderView;
    const ordered = orderByBudget(report.findings, view.budget);
    const rowIds = view.budget.rows.map((row) => row.finding_id);
    expect(
      ordered.slice(0, rowIds.length).map((f) => f.record.finding_id),
    ).toEqual(rowIds);
    expect(orderByBudget(report.findings)).toBe(report.findings);
  });

  it("rejects malformed views", () => {
    const view = readJson("stakeholder/breach-pattern.json") as StakeholderView;
    expect(isStakeholderView(null)).toBe(false);
    expect(isStakeholderView({ ...view, budget: {} })).toBe(false);
    const [firstId] = Object.keys(view.blocks);
    expect(
      isStakeholderView({
        ...view,
        blocks: { [firstId]: { ...view.blocks[firstId], fix: null } },
      }),
    ).toBe(false);
  });
});

describe("stakeholder view: cost-first intro and report download", () => {
  const report = readJson("reports/breach-pattern.json") as ReviewReport;
  const view = readJson("stakeholder/breach-pattern.json") as StakeholderView;
  const merged = withStakeholderView(report, view);

  it("leads the intro with what the fixes cost", () => {
    expect(stakeholderSummary(merged).intro).toBe(
      "11 items need attention. 6 of them are free settings changes; the recommended fixes add $29.86 + usage a month to the AWS bill and take 2 to 5 working days of engineering.",
    );
    expect(stakeholderSummary(report).intro).toMatch(
      /^6 rule results were reported/,
    );
    const allFree = { ...merged, budget: budget({ free_count: 3 }) };
    expect(stakeholderSummary(allFree).intro).toBe(
      "3 items need attention, and every fix is free on the AWS bill. Together they take 1 to 4 hours of engineering.",
    );
  });

  it("puts the budget and each card's costs in the downloaded report", () => {
    const html = buildReportHtml(merged, [], "Breach pattern");
    expect(html).toContain("<h2>What it costs to fix</h2>");
    expect(html).toContain("Cost of not fixing.");
    expect(html).toContain("IBM Cost of a Data Breach Report 2026");
    expect(buildReportHtml(report, [], "x")).not.toContain(
      "What it costs to fix",
    );
  });

  it("escapes stakeholder text in the downloaded report", () => {
    const [first] = merged.findings;
    const hostile = {
      ...merged,
      findings: [
        {
          ...first,
          stakeholder: {
            ...first.stakeholder!,
            analogy: '<img src=x onerror="alert(1)">',
          },
        },
      ],
    };
    const html = buildReportHtml(hostile, [], "x");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});
