import { publicUnverified, UNVERIFIED_NOTE } from "./unverified";
import type { ChatCitation, ChatTurn, ReportFinding, ReviewReport } from "./contracts";
import type { DemoEntry, ReviewerNote } from "./demos";
import { evidenceLabel, notesForTurn, reportSnapshotLabel } from "./report-review";
import {
  EVIDENCE_STATE_LABELS,
  MONEY_NOTE,
  SAFETY_SENTENCE,
  SOURCE_LABELS,
  TIER_EXPLANATIONS,
  TIER_LABELS,
  TIER_LEGEND,
  briefCardFor,
  briefCoverage,
  cardTitle,
  evidenceStateFor,
  tierFor,
} from "./stakeholder-brief";
import { QUOTE_OMITTED_NOTE } from "./money-policy";
import { publicRecord, publicTurn } from "./public-projection";
import { assessmentFor, assessmentLabel } from "./assessment";
import {
  declarationScopeMessage,
  independentCheckLabel,
  qualityMessage,
  scopeMessage,
} from "./analysis-quality";

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
    return citation.quote_omitted
      ? `<li>${link}: <span class="meta">${escapeHtml(QUOTE_OMITTED_NOTE)}</span></li>`
      : `<li>${link}: “${escapeHtml(citation.quote)}”</li>`;
  }
  const kind = { finding: "Finding", resource: "Resource", requirement: "Requirement" }[
    citation.kind
  ];
  return `<li>${kind}: ${escapeHtml(citationLabel(citation))}</li>`;
}

// A finding's Stakeholder Brief text, the same as the on-screen view. No
// prices; the tier is a qualitative label.
function briefHtml(finding: ReportFinding): string {
  const card = briefCardFor(finding);
  const tier = tierFor(card);
  const parts: Array<[string, string]> =
    card.kind === "curated"
      ? [
          ["Risk", card.entry.risk],
          ["Work proposed", card.entry.work],
          ["Helps prevent", card.entry.prevents],
          ["Still exposed", card.entry.stillExposed],
        ]
      : card.kind === "summary"
        ? [
            ["Risk", card.summary],
            ["Work proposed", card.action],
          ]
        : [];
  const source =
    card.kind === "curated"
      ? SOURCE_LABELS.curated
      : card.kind === "summary"
        ? `${card.writtenBy === "model" ? "AI-written" : "Hand-written"} plain summary. ${SOURCE_LABELS[card.writtenBy]}`
        : card.notObservable
          ? SOURCE_LABELS.notObservable
          : SOURCE_LABELS.technical;
  const analogy =
    card.kind === "curated" && card.entry.analogy
      ? `<p><strong>In farm terms.</strong> ${escapeHtml(card.entry.analogy)}</p>`
      : "";
  const biggerIf =
    card.kind === "curated" && card.entry.biggerIf
      ? ` Bigger if ${escapeHtml(card.entry.biggerIf)}`
      : "";
  const commitment = tier
    ? `${escapeHtml(TIER_LABELS[tier])}. ${escapeHtml(TIER_EXPLANATIONS[tier])}${biggerIf}`
    : "Unclassified: there is no typical commitment for this kind of finding.";
  return `<div class="brief">
      <p><strong>Stakeholder Brief: ${escapeHtml(cardTitle(card))}</strong> <span class="meta">${escapeHtml(source)}</span></p>
      ${card.kind === "curated" ? `<p class="meta">What the evidence shows: ${escapeHtml(EVIDENCE_STATE_LABELS[evidenceStateFor(card.concern)])} Principle: ${escapeHtml(card.entry.principle)}.</p>` : ""}
      ${analogy}
      ${parts.map(([label, text]) => `<p><strong>${label}.</strong> ${escapeHtml(text)}</p>`).join("")}
      <p><strong>Typical commitment.</strong> ${commitment}</p>
    </div>`;
}

function reviewerNoteHtml(note: ReviewerNote): string {
  return `<aside class="reviewer-note"><strong>Reviewer note · ${escapeHtml(note.verdict)}</strong><p>${escapeHtml(note.note)}</p></aside>`;
}

// A saved answer as the public sees it: cost figures removed (by the server,
// or here for older saved answers), code syntax kept, priced quotes omitted.
function answerHtml(turn: ChatTurn): string {
  const unsupported = (turn.unsupported ?? []).length
    ? `<aside><strong>Unsupported</strong><p>The reference check could not confirm these statements. Check them before acting.</p>${turn.unsupported!.map((text) => `<p>${escapeHtml(text)}</p>`).join("")}</aside>`
    : "";
  const html = turn.answer.map((p) => paragraphHtml(p.text)).join("") + unsupported;
  const removed = turn.answer.some((p) => p.amounts_removed);
  return removed ? `${html}<p class="meta">${escapeHtml(MONEY_NOTE)}</p>` : html;
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
      const { record, changed } = publicRecord(finding.record);
      const moneyRemoved = changed.some((field) => !field.startsWith("plain."));
      const quoteOmitted = changed.includes("citation.exact_text_span (omitted)");
      return `
    <article class="finding">
      <h3>${escapeHtml(record.finding)}</h3>
      ${independentCheckLabel(finding) ? `<p>${escapeHtml(independentCheckLabel(finding))}</p>` : ""}
      <p class="meta">${escapeHtml(assessmentLabel(finding))} · assessment source: ${escapeHtml(assessmentFor(finding).source)}</p>
      <p class="meta">${escapeHtml(evidenceLabel(record.type))} · ${escapeHtml(record.category)} · ${escapeHtml(record.type)} · evidence confidence ${Math.round(record.confidence * 100)}% (heuristic, not correctness probability)</p>
      ${notes
        .filter((note) => note.findingId === record.finding_id)
        .map(reviewerNoteHtml)
        .join("")}
      <p><strong>Evidence.</strong> ${escapeHtml(record.evidence)}</p>
      <p><strong>Risk.</strong> ${escapeHtml(record.risk_impact)}</p>
      <p><strong>Recommendation.</strong> ${escapeHtml(record.recommendation)}</p>
      ${moneyRemoved ? `<p class="meta">${escapeHtml(MONEY_NOTE)}</p>` : ""}
      ${briefHtml(finding)}
      ${
        record.citation
          ? `<p class="source"><strong>Source.</strong> ${escapeHtml(record.citation.heading_path)}: ${!quoteOmitted ? `“${escapeHtml(record.citation.exact_text_span)}”` : `<span class="meta">${escapeHtml(QUOTE_OMITTED_NOTE)}</span>`}${
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
        .map((saved) => publicTurn(saved).turn)
        .map(
          (turn) => `
    <article class="turn">
      <p class="q"><strong>Q.</strong> ${escapeHtml(turn.question)}</p>
      ${notesForTurn(turn, notes).map(reviewerNoteHtml).join("")}
      ${answerHtml(turn)}
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
  .brief { border-top: 1px dashed #c5d0d9; margin-top: .6rem; padding-top: .4rem; }
  .reviewer-note { border-left: 4px solid #7f500f; background: #faf1e2; padding: .4rem .8rem; margin: .5rem 0; }
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
<h2>Review coverage</h2><p>${escapeHtml(declarationScopeMessage(report.review_scope))}</p>
<p>${escapeHtml(briefCoverage(report).headline)}</p>
${report.analysis_scope ? `<h2>Configuration scope</h2><p>${escapeHtml(scopeMessage(report.analysis_scope))}</p>` : ""}
${(report.deeper_jobs ?? []).map((job) => `<p>Deeper review of ${escapeHtml(job.parent_finding_id)}: ${escapeHtml(job.status)}. Saved findings reflect completed work only.</p>`).join("")}
${(report.deeper_reviews ?? []).map((run) => `<p>Deeper review of ${escapeHtml(run.parent_finding_id)}: ${escapeHtml(qualityMessage(run.analysis_quality))}</p>`).join("")}
${report.report_projection?.excluded_child_count ? "<p>Some saved deeper findings could not be included. Report completeness and totals are limited.</p>" : ""}
${demo ? `<h2>Demo source and review corrections</h2><p>${escapeHtml(demo.source)} · ${escapeHtml(demo.license)}</p><p>${escapeHtml(demo.disclaimer)}</p>${safeHref(demo.sourceUrl) ? `<p><a href="${escapeHtml(safeHref(demo.sourceUrl))}">Original source</a></p>` : ""}<p>Original generated text is preserved. Reviewer notes correct or qualify it, including saved answers. Annotation format: demo-review@1; historical review date not recorded.</p>${notes.map(reviewerNoteHtml).join("")}` : ""}
<h2>Requirements used</h2>
<ul>${baseline || "<li>None recorded.</li>"}</ul>
${report.findings.some(({ record }) => record.parent_finding_id) && !report.report_projection?.children_available ? "<p>The Stakeholder Brief covers the original report. Added deeper findings are listed separately below.</p>" : ""}
<h2>Findings (${report.findings.length})</h2>
<p class="meta">Each finding has its technical record and its Stakeholder Brief explanation. Commitment labels (${escapeHtml(Object.values(TIER_LABELS).join(", "))}): ${escapeHtml(TIER_LEGEND)} ${escapeHtml(SAFETY_SENTENCE)} No cost estimates are published.</p>
${findings}
${
  publicUnverified(report.unverified_findings).length ||
  report.analysis_quality?.reason_codes.includes("model_unavailable")
    ? `<section><h2>Unable to verify</h2><p>${escapeHtml(UNVERIFIED_NOTE)}</p>${report.analysis_quality?.reason_codes.includes("model_unavailable") ? "<p>The AI analysis failed or timed out.</p>" : ""}${publicUnverified(
        report.unverified_findings,
      )
        .map(
          (item) =>
            `<article><strong>Unverified claim</strong><h3>${escapeHtml(item.finding)}</h3><p>${escapeHtml(item.resource)}</p><p>${escapeHtml(item.reason)}</p><p>${escapeHtml(item.evidence)}</p><p>Recommendation withheld.</p></article>`,
        )
        .join("")}</section>`
    : ""
}
<h2>Conversation</h2>
${conversation}
<footer>
  Generated by ArchiBrief. AI-assisted review snapshot: cited answer paragraphs reference the review's
  findings or AWS guidance; Unsupported notes could not be confirmed. It describes evidence, not compliance certification, and it
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
