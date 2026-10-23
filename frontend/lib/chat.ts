import type {
  BudgetSummary,
  ChatCitation,
  ChatTurn,
  ReviewReport,
  StakeholderCard,
} from "./contracts";
import type { DemoEntry, ReviewerNote } from "./demos";
import { evidenceLabel, notesForTurn, reportSnapshotLabel } from "./report-review";
import { formatDollars, formatMonthly } from "./workflow";
import { assessmentFor, assessmentLabel } from "./assessment";
import { qualityMessage } from "./analysis-quality";

// Plain messages for the chat API's error codes (backend/lambdas/
// ask_question ERROR_MESSAGES). The server's own text is never shown, so
// the UI stays in control of the wording.
const CHAT_ERRORS: Record<string, string> = {
  invalid_request: "That request couldn't be read. Reload the page and try again.",
  invalid_question: "Please ask in plain text, in under 500 characters.",
  chat_not_public: "Questions are paused right now.",
  review_not_found: "This review doesn't exist or has expired.",
  review_not_complete: "Questions open once the review is finished.",
  request_in_progress: "That question is still being answered. Try again in a moment.",
  request_expired: "That saved answer has expired. Ask it again to start a new question.",
  request_conflict: "The question changed after it was sent. Start a new question.",
  review_quota_exhausted: "You've used this review's questions.",
  daily_cap_reached:
    "Today's free questions are used up. Try again tomorrow. Suggested answers already given still work.",
  too_many_blocked: "Too many questions on this review couldn't be processed.",
  too_many_failed: "Answers on this review keep failing. Try again later.",
  answer_failed: "The answer couldn't be completed. Your question wasn't counted.",
  answer_timeout: "The answer took too long. Your question wasn't counted.",
  chat_paused: "Chat is paused right now.",
  guardrails_unavailable: "Questions can't be checked right now. Try again shortly.",
  chat_busy: "Lots of questions at once. Try again in a moment.",
};

export function chatErrorMessage(code: string): string {
  return CHAT_ERRORS[code] ?? "Something went wrong asking that question.";
}

export function remainingLabel(remaining: number, limit: number): string {
  if (remaining <= 0) return `You've used this review's ${limit} questions`;
  return `${remaining} of ${limit} question${limit === 1 ? "" : "s"} left on this review`;
}

export function newClientRequestId(): string {
  return crypto.randomUUID();
}

export const MAX_QUESTION_CHARS = 500;

export function citationLabel(citation: ChatCitation): string {
  switch (citation.kind) {
    case "finding":
      return citation.title;
    case "source":
      return citation.heading_path || "AWS guidance";
    case "resource":
      return citation.address;
    case "requirement":
      return citation.label;
  }
}

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

// Only http(s) links from the server's own citation records are made
// clickable; anything else is shown as text.
function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function paragraphHtml(text: string): string {
  // Code blocks the server kept (at most one, 20 lines) render as <pre>.
  return text
    .split(/```/)
    .map((part, i) =>
      i % 2 === 1
        ? `<pre>${escapeHtml(part.replace(/^\n/, ""))}</pre>`
        : part.trim()
          ? `<p>${escapeHtml(part.trim()).replace(/\n/g, "<br>")}</p>`
          : "",
    )
    .join("");
}

function citationHtml(citation: ChatCitation): string {
  if (citation.kind === "source") {
    const href = safeHref(citation.source_url);
    const heading = escapeHtml(citation.heading_path || "AWS guidance");
    const link = href ? `<a href="${escapeHtml(href)}">${heading}</a>` : heading;
    return `<li>${link}: “${escapeHtml(citation.quote)}”</li>`;
  }
  const kind = { finding: "Finding", resource: "Resource", requirement: "Requirement" }[
    citation.kind
  ];
  return `<li>${kind}: ${escapeHtml(citationLabel(citation))}</li>`;
}

// The budget summary as a table, the same figures as the stakeholder view.
function budgetHtml(budget: BudgetSummary): string {
  const rows = budget.rows
    .map(
      (row) =>
        `<tr><td>${escapeHtml(row.title)}${row.subject ? ` <span class="meta">${escapeHtml(row.subject)}</span>` : ""}</td><td>${escapeHtml(formatMonthly(row.monthly_known, row.has_unpriced))}</td><td>${escapeHtml(row.effort_label)}</td><td>${escapeHtml(row.verdict_label)}</td></tr>`,
    )
    .join("");
  const optional =
    budget.monthly_optional > 0
      ? `, plus ${escapeHtml(formatDollars(budget.monthly_optional))}/month for optional extras`
      : "";
  const unpriced = budget.unpriced_items.length
    ? ` Not included because they depend on usage or size: ${escapeHtml(budget.unpriced_items.join(", "))}.`
    : "";
  return `
<p><strong>${escapeHtml(formatMonthly(budget.monthly_recommended, budget.recommended_has_unpriced))}/month</strong> more on the AWS bill for the recommended fixes${optional}. Engineering time: ${escapeHtml(budget.effort_label)}. Free fixes: ${budget.free_count} of ${budget.item_count}.</p>
<table><thead><tr><th>Fix</th><th>Monthly cost</th><th>Effort</th><th>Verdict</th></tr></thead><tbody>${rows}</tbody></table>
<p class="meta">${unpriced} ${escapeHtml(budget.note)} Effort is summed per finding; overlapping fixes may share work.</p>`;
}

function stakeholderHtml(card: StakeholderCard): string {
  const plain = `<p><strong>In plain terms.</strong> ${escapeHtml(card.title)}. ${escapeHtml(card.analogy)} ${escapeHtml(card.what_could_happen)}</p>`;
  if (!card.fix || !card.inaction) return plain;
  const lines = card.fix.lines
    .map((line) =>
      line.monthly_high === null
        ? `${line.label}: ${line.basis}`
        : `${line.label}: ${formatDollars(line.monthly_high)}/month (${line.basis})`,
    )
    .join("; ");
  const source =
    card.inaction.source_name && safeHref(card.inaction.source_url ?? "")
      ? ` Source: <a href="${escapeHtml(safeHref(card.inaction.source_url ?? ""))}">${escapeHtml(card.inaction.source_name)}</a>.`
      : "";
  const method = card.inaction.method ? ` ${escapeHtml(card.inaction.method)}` : "";
  return `${plain}
      <p><strong>Cost to fix.</strong> ${escapeHtml(formatMonthly(card.fix.monthly_known, card.fix.has_unpriced))}/month: ${escapeHtml(lines)}. Engineering time: ${escapeHtml(card.fix.effort_label)}. <span class="meta">${escapeHtml(card.verdict_label)}</span></p>
      <p><strong>Cost of not fixing.</strong> ${escapeHtml(card.inaction.headline)}. ${escapeHtml(card.inaction.detail)}${method}${source} Industry figures are context, not a predicted loss for this system.</p>`;
}

function reviewerNoteHtml(note: ReviewerNote): string {
  return `<aside class="reviewer-note"><strong>Reviewer note · ${escapeHtml(note.verdict)}</strong><p>${escapeHtml(note.note)}</p></aside>`;
}

// One self-contained HTML file: inline CSS, no scripts, print-friendly
// (ADR-0050 §10). Every value is escaped; model text is never inserted as
// HTML.
export function buildReportHtml(
  report: ReviewReport,
  transcript: ChatTurn[],
  title: string,
  demo?: DemoEntry | null,
): string {
  const notes = demo?.reviewerNotes ?? [];
  const findings = report.findings
    .map((finding) => {
      const { record, stakeholder } = finding;
      return `
    <article class="finding">
      <h3>${escapeHtml(record.finding)}</h3>
      <p class="meta">${escapeHtml(assessmentLabel(finding))} · assessment source: ${escapeHtml(assessmentFor(finding).source)}</p>
      <p class="meta">${escapeHtml(evidenceLabel(record.type))} · ${escapeHtml(record.category)} · ${escapeHtml(record.type)} · evidence confidence ${Math.round(record.confidence * 100)}% (heuristic, not correctness probability)</p>
      ${notes
        .filter((note) => note.findingId === record.finding_id)
        .map(reviewerNoteHtml)
        .join("")}
      <p><strong>Evidence.</strong> ${escapeHtml(record.evidence)}</p>
      <p><strong>Risk.</strong> ${escapeHtml(record.risk_impact)}</p>
      <p><strong>Recommendation.</strong> ${escapeHtml(record.recommendation)}</p>
      ${stakeholder ? stakeholderHtml(stakeholder) : ""}
      ${
        record.citation
          ? `<p class="source"><strong>Source.</strong> ${escapeHtml(record.citation.heading_path)}: “${escapeHtml(record.citation.exact_text_span)}”${
              safeHref(record.citation.source_url)
                ? ` (<a href="${escapeHtml(safeHref(record.citation.source_url))}">${escapeHtml(record.citation.source_url)}</a>)`
                : ""
            }</p>`
          : ""
      }
    </article>`;
    })
    .join("");
  const baseline = report.baseline_answers
    .map(
      (a) =>
        `<li><strong>${escapeHtml(a.label)}:</strong> ${escapeHtml(a.value)} <span class="meta">(${escapeHtml(a.outcome)})</span></li>`,
    )
    .join("");
  const conversation = transcript.length
    ? transcript
        .map(
          (turn) => `
    <article class="turn">
      <p class="q"><strong>Q.</strong> ${escapeHtml(turn.question)}</p>
      ${notesForTurn(turn, notes).map(reviewerNoteHtml).join("")}
      ${turn.answer.map((p) => paragraphHtml(p.text)).join("")}
      ${
        turn.answer.some((p) => p.citations.length)
          ? `<ul class="cites">${turn.answer
              .flatMap((p) => p.citations)
              .map(citationHtml)
              .join("")}</ul>`
          : ""
      }
      <p class="meta">${escapeHtml(turn.status.replace("_", " "))}${turn.model_id ? ` · ${escapeHtml(turn.model_id)}` : ""}${turn.prompt_version ? ` · ${escapeHtml(turn.prompt_version)}` : ""}</p>
    </article>`,
        )
        .join("")
    : "<p>No questions were asked.</p>";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
  body { font: 15px/1.55 Georgia, serif; color: #131c24; background: #fff; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }
  h1, h2, h3 { font-family: system-ui, sans-serif; line-height: 1.25; }
  h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #c5d0d9; padding-bottom: .3rem; }
  h3 { font-size: 1rem; margin: 0 0 .3rem; }
  .finding, .turn { border: 1px solid #c5d0d9; border-radius: 8px; padding: .8rem 1rem; margin: .8rem 0; break-inside: avoid; }
  .meta { color: #43596c; font: 12px/1.4 system-ui, sans-serif; }
  .q { font-family: system-ui, sans-serif; }
  .cites { font-size: 13px; color: #43596c; }
  table { width: 100%; border-collapse: collapse; font: 13px/1.4 system-ui, sans-serif; }
  th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #c5d0d9; vertical-align: top; }
  pre { background: #f4f7f9; padding: .6rem; border-radius: 6px; overflow-x: auto; font-size: 12px; }
  a { color: #235f7a; }
  footer { margin-top: 2rem; color: #43596c; font: 12px/1.5 system-ui, sans-serif; }
  @media print { body { margin: 0; } a { color: inherit; } }
</style>
</head>
<body>
<h1>${escapeHtml(title)}</h1>
<p class="meta">${escapeHtml(report.terraform_repo_ref)} · ${escapeHtml(report.created_at)} · review ${escapeHtml(report.review_id)}</p>
<p class="meta">${escapeHtml(reportSnapshotLabel(report.findings))}</p>
<h2>Analysis quality</h2><p>${escapeHtml(qualityMessage(report.analysis_quality))}</p>
${(report.deeper_reviews ?? []).map((run) => `<p>Deeper review of ${escapeHtml(run.parent_finding_id)}: ${escapeHtml(qualityMessage(run.analysis_quality))}</p>`).join("")}
${report.report_projection?.excluded_child_count ? "<p>Some saved deeper findings could not be included. Report completeness and totals are limited.</p>" : ""}
${demo ? `<h2>Demo source and review corrections</h2><p>${escapeHtml(demo.source)} · ${escapeHtml(demo.license)}</p><p>${escapeHtml(demo.disclaimer)}</p>${safeHref(demo.sourceUrl) ? `<p><a href="${escapeHtml(safeHref(demo.sourceUrl))}">Original source</a></p>` : ""}<p>Original generated text is preserved. Reviewer notes correct or qualify it, including saved answers. Annotation format: demo-review@1; historical review date not recorded.</p>${notes.map(reviewerNoteHtml).join("")}` : ""}
<h2>Requirements used</h2>
<ul>${baseline || "<li>None recorded.</li>"}</ul>
${report.findings.some(({ record }) => record.parent_finding_id) && !report.report_projection?.children_available ? "<p>Budget totals and guided explanations cover the original report. Added deeper findings are listed separately below and are not included in those totals.</p>" : ""}
${report.budget ? `<h2>What it costs to fix</h2>${budgetHtml(report.budget)}` : ""}
<h2>Findings (${report.findings.length})</h2>
${findings}
<h2>Conversation</h2>
${conversation}
<footer>
  Generated by ArchiBrief. AI-assisted and grounded in this review snapshot: every answer cites the
  review's own findings or AWS guidance. It describes evidence, not compliance certification, and it
  can't see live AWS state.
</footer>
</body>
</html>
`;
}

export function downloadFile(filename: string, contents: string, type: string): void {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
