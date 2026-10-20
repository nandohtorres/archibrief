import type { BudgetSummary as Budget, Verdict } from "@/lib/contracts";
import { budgetHeadline, formatDollars, formatMonthly } from "@/lib/workflow";

// Shared with the finding cards, so a verdict looks the same everywhere.
export const verdictClass: Record<Verdict, string> = {
  "fix-today": "urgent",
  "quick-win": "quick",
  "worth-the-money": "worth",
  "when-budget-allows": "optional",
};

interface BudgetSummaryProps {
  budget: Budget;
  // Distinguishes the copy at the top of the view from the one at the
  // bottom, for heading ids.
  placement: "top" | "bottom";
  onOpenFinding?: (findingId: string) => void;
}

export function BudgetSummary({ budget, placement, onOpenFinding }: BudgetSummaryProps) {
  const headingId = `budget-heading-${placement}`;
  return (
    <section className="budget-summary" aria-labelledby={headingId}>
      <h3 id={headingId}>{placement === "top" ? "What it costs to fix" : "Budget summary"}</h3>
      <p className="budget-headline">{budgetHeadline(budget)}</p>
      <div className="budget-stats">
        <div>
          <span>Recommended fixes</span>
          <strong>
            {formatMonthly(budget.monthly_recommended, budget.recommended_has_unpriced)}
            <small> /month</small>
          </strong>
          <p>
            more on the AWS bill
            {budget.monthly_optional > 0 &&
              `, plus ${formatDollars(budget.monthly_optional)}/month for optional extras`}
          </p>
        </div>
        <div>
          <span>Engineering time</span>
          <strong>{budget.effort_label}</strong>
          <p>for one engineer who knows the system</p>
        </div>
        <div>
          <span>Free fixes</span>
          <strong>
            {budget.free_count} of {budget.item_count}
          </strong>
          <p>settings changes with no ongoing AWS cost</p>
        </div>
      </div>

      {budget.rows.length > 0 && (
        <div className="budget-table-wrap">
          <table className="budget-table">
            <thead>
              <tr>
                <th scope="col">Fix</th>
                <th scope="col">Monthly cost</th>
                <th scope="col">Effort</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {budget.rows.map((row) => (
                <tr key={row.finding_id}>
                  <td>
                    {onOpenFinding ? (
                      <button
                        type="button"
                        className="budget-row-link"
                        onClick={() => onOpenFinding(row.finding_id)}
                      >
                        {row.title}
                      </button>
                    ) : (
                      row.title
                    )}
                    {row.subject && <small>{row.subject}</small>}
                  </td>
                  <td className="num" data-label="Monthly cost">
                    {formatMonthly(row.monthly_known, row.has_unpriced)}
                  </td>
                  <td className="num" data-label="Effort">
                    {row.effort_label}
                  </td>
                  <td>
                    <span className={`verdict-tag ${verdictClass[row.verdict]}`}>
                      {row.verdict_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="budget-note">
        {budget.unpriced_items.length > 0 && (
          <>
            Not included because they depend on usage or size: {budget.unpriced_items.join(", ")}
            .{" "}
          </>
        )}
        {budget.note}
      </p>
    </section>
  );
}
