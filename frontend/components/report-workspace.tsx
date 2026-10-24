"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import type {
  AnalysisQuality,
  ChatTurn,
  DemoChat,
  DeeperJob,
  ReportFinding,
  ReviewReport,
} from "@/lib/contracts";
import { isReviewReport } from "@/lib/contracts";
import { isArchitectureGraph, type ArchitectureGraph } from "@/lib/architecture";
import { fetchReview, getApiBaseUrl, requestDeeperFinding } from "@/lib/api";
import { reviewerNotesById, type DemoEntry } from "@/lib/demos";
import { buildReportHtml, downloadFile } from "@/lib/chat";
import { buildReportExport, reportSnapshotLabel, withEvidenceLabel } from "@/lib/report-review";
import {
  filterAndSortFindings,
  formatFindingId,
  reportSourceLabels,
  reportTitle,
  type FindingFilter,
  type FindingSort,
  type ReportSource,
} from "@/lib/workflow";
import { ArchitectureView } from "./architecture-view";
import { FindingDetail } from "./finding-detail";
import { GuidedReport } from "./guided-report";
import { ReportQuestions } from "./report-questions";
import { AssessmentTag } from "./assessment-tag";
import { qualityMessage, scopeMessage } from "@/lib/analysis-quality";

interface ReportWorkspaceProps {
  report: ReviewReport;
  source: ReportSource;
  // The demo's index entry (source, license, reviewer notes) and its
  // pregenerated suggested answers, when this is a demo review.
  demo?: DemoEntry | null;
  demoChat?: DemoChat | null;
  // A demo's diagram, from its saved file. Other reports carry their own
  // (report.architecture); a report without one shows no diagram.
  architecture?: ArchitectureGraph | null;
  onNewReview: () => void;
}

const DEFAULT_DETAIL_PANE_WIDTH = 75;
const MIN_DETAIL_PANE_WIDTH = 45;
const MAX_DETAIL_PANE_WIDTH = 85;

export function ReportWorkspace({
  report: initialReport,
  source,
  demo = null,
  demoChat = null,
  architecture: demoArchitecture = null,
  onNewReview,
}: ReportWorkspaceProps) {
  const [report, setReport] = useState(initialReport);
  const reviewerNotes = useMemo(() => reviewerNotesById(demo), [demo]);
  const architecture =
    demoArchitecture ?? (isArchitectureGraph(report.architecture) ? report.architecture : null);
  // A demo has a real title; other reports are named from their repository label.
  const title = demo ? demo.title : reportTitle(report.terraform_repo_ref);
  const [view, setView] = useState<"technical" | "stakeholder">("technical");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FindingFilter>("all");
  const [sort, setSort] = useState<FindingSort>("priority");
  const [findings, setFindings] = useState<ReportFinding[]>(report.findings.map(withEvidenceLabel));
  const [architectureFocus, setArchitectureFocus] = useState<{
    findingId: string;
    at: number;
  } | null>(null);
  const [selectedId, setSelectedId] = useState(report.findings[0]?.record.finding_id ?? "");
  const [status, setStatus] = useState("");
  useEffect(() => {
    const active =
      report.deeper_jobs?.filter((job) => job.status === "pending" || job.status === "running") ??
      [];
    if (source !== "live" || active.length === 0) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    function timedOut() {
      controller.abort();
      clearTimeout(timer);
      setStatus(
        "We couldn't confirm the deeper job's status in time. Your report remains available. Reload to check the saved result.",
      );
    }
    // Stop even if an individual status fetch never resolves.
    const deadlineTimer = setTimeout(
      timedOut,
      Math.max(
        0,
        Math.min(8 * 60 * 1000, Math.max(...active.map((job) => job.deadline)) * 1000 - Date.now()),
      ),
    );
    async function poll() {
      if (active.every((job) => job.deadline * 1000 <= Date.now())) {
        timedOut();
        return;
      }
      try {
        const refreshed = await fetchReview(report.review_id, controller.signal);
        if (controller.signal.aborted) return;
        if (!isReviewReport(refreshed)) throw new Error("Report status unavailable");
        setReport(refreshed);
        setFindings(refreshed.findings.map(withEvidenceLabel));
        const finished = refreshed.deeper_jobs?.find(
          (job) =>
            active.some((a) => a.job_id === job.job_id) &&
            (job.status === "complete" || job.status === "failed"),
        );
        if (finished) {
          setStatus(
            finished.status === "complete"
              ? "Deeper analysis finished. The saved report has been refreshed."
              : "Deeper analysis could not finish. Your original report and saved findings remain available.",
          );
          const child = refreshed.findings.find(
            (f) => f.record.parent_finding_id === finished.parent_finding_id,
          );
          if (child)
            setSelectedId((current) =>
              current === finished.parent_finding_id ? child.record.finding_id : current,
            );
        }
      } catch {
        if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
      }
    }
    timer = setTimeout(poll, 2000);
    return () => {
      controller.abort();
      clearTimeout(timer);
      clearTimeout(deadlineTimer);
    };
  }, [report.review_id, report.deeper_jobs, source]);
  const [questionSeed, setQuestionSeed] = useState("");
  const [seedFindingId, setSeedFindingId] = useState("");
  const [transcript, setTranscript] = useState<ChatTurn[]>([]);
  const [detailPaneWidth, setDetailPaneWidth] = useState(DEFAULT_DETAIL_PANE_WIDTH);
  const workspaceRef = useRef<HTMLDivElement>(null);

  const visibleFindings = useMemo(
    () => filterAndSortFindings(findings, query, filter, sort),
    [findings, query, filter, sort],
  );
  const selected =
    visibleFindings.find(({ record }) => record.finding_id === selectedId) ?? visibleFindings[0];
  const ruleCount = findings.filter(
    ({ record }) => record.type === "deterministic-rule-result",
  ).length;
  const assumptionCount = findings.filter(({ record }) => record.type === "assumption").length;

  function selectFinding(findingId: string) {
    setDetailPaneWidth(DEFAULT_DETAIL_PANE_WIDTH);
    setSelectedId(findingId);
    if (window.matchMedia("(max-width: 800px)").matches) {
      window.requestAnimationFrame(() =>
        document.getElementById("finding-detail")?.scrollIntoView({ block: "start" }),
      );
    }
  }

  function openTechnicalFinding(findingId: string) {
    setDetailPaneWidth(DEFAULT_DETAIL_PANE_WIDTH);
    setView("technical");
    setFilter("all");
    setQuery("");
    setSelectedId(findingId);
    window.requestAnimationFrame(() =>
      document.getElementById("finding-detail")?.scrollIntoView({ block: "start" }),
    );
  }

  function resizeDetailPane(clientX: number) {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds || bounds.width === 0) return;

    const nextWidth = ((bounds.right - clientX) / bounds.width) * 100;
    setDetailPaneWidth(Math.min(MAX_DETAIL_PANE_WIDTH, Math.max(MIN_DETAIL_PANE_WIDTH, nextWidth)));
  }

  function handleResizePointerDown(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeDetailPane(event.clientX);
  }

  function handleResizePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    resizeDetailPane(event.clientX);
  }

  function handleResizeKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setDetailPaneWidth((current) => Math.min(MAX_DETAIL_PANE_WIDTH, current + 5));
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setDetailPaneWidth((current) => Math.max(MIN_DETAIL_PANE_WIDTH, current - 5));
    }
    if (event.key === "Home") {
      event.preventDefault();
      setDetailPaneWidth(MAX_DETAIL_PANE_WIDTH);
    }
    if (event.key === "End") {
      event.preventDefault();
      setDetailPaneWidth(MIN_DETAIL_PANE_WIDTH);
    }
  }

  function askAboutFinding(finding: ReportFinding) {
    if (finding.record.parent_finding_id) {
      setStatus(
        "Questions currently use the original report. Choose an original finding to ask about it; deeper findings are included in this session's download.",
      );
      return;
    }
    setQuestionSeed(`Explain this finding: ${finding.record.finding}`);
    setSeedFindingId(finding.record.finding_id);
    window.requestAnimationFrame(() =>
      document.getElementById("ask-review")?.scrollIntoView({ block: "start" }),
    );
  }

  const consumeQuestionSeed = useCallback(() => setQuestionSeed(""), []);

  function showOnArchitecture(findingId: string) {
    setArchitectureFocus({ findingId, at: Date.now() });
    setStatus(`${formatFindingId(findingId)} is shown in the architecture section.`);
    document.getElementById("architecture-impact")?.scrollIntoView({ block: "start" });
  }

  async function goDeeper(findingId: string) {
    // The sample is precomputed and has no stored review behind it, so
    // there is nothing to take deeper (and no paid run to start).
    if (source === "sample" || source === "demo") {
      setStatus(
        `Going deeper runs a new analysis on your own reviews. ${formatFindingId(findingId)} is part of the ${source === "demo" ? "saved demo review" : "precomputed sample"}.`,
      );
      return;
    }
    if (!getApiBaseUrl()) {
      setStatus(
        `Fixture only: ${formatFindingId(findingId)} would create a versioned child finding. The endpoint is not deployed.`,
      );
      return;
    }
    try {
      const result = (await requestDeeperFinding(report.review_id, findingId)) as {
        findings?: ReportFinding[];
        analysis_quality?: AnalysisQuality;
        job?: DeeperJob;
      };
      if (result.job) {
        const job = result.job;
        setReport((current) => ({
          ...current,
          deeper_jobs: [
            ...(current.deeper_jobs ?? []).filter((saved) => saved.job_id !== job.job_id),
            job,
          ],
        }));
        setStatus(
          "Deeper analysis is running in the background. You can keep using this report or reload to check its saved status.",
        );
        return;
      }
      const newFindings = result.findings ?? [];
      if (newFindings.length === 0) {
        try {
          const refreshed = await fetchReview(report.review_id);
          if (isReviewReport(refreshed)) {
            setReport(refreshed);
            setFindings(refreshed.findings.map(withEvidenceLabel));
          }
        } catch {
          /* The completed run can be recovered on reload. */
        }
        setStatus(
          `The deeper request for ${formatFindingId(findingId)} returned no new findings. ${qualityMessage(result.analysis_quality)}`,
        );
        return;
      }
      try {
        const refreshed = await fetchReview(report.review_id);
        if (
          isReviewReport(refreshed) &&
          refreshed.report_projection?.children_available &&
          newFindings.every((child) =>
            refreshed.findings.some((f) => f.record.finding_id === child.record.finding_id),
          )
        ) {
          setReport(refreshed);
          setFindings(refreshed.findings.map(withEvidenceLabel));
          selectFinding(newFindings[0].record.finding_id);
          setStatus(
            `Deeper findings saved. The report, guided budget, diagram and chat now use the saved findings. ${qualityMessage(result.analysis_quality)}`,
          );
          return;
        }
      } catch {
        // Results were saved by POST, but a failed read must not claim the
        // original budget/diagram has been refreshed. Keep the bounded view.
      }
      setFindings((current) => {
        const known = new Set(current.map(({ record }) => record.finding_id));
        return [
          ...current,
          ...newFindings
            .filter(({ record }) => !known.has(record.finding_id))
            .map(withEvidenceLabel),
        ];
      });
      selectFinding(newFindings[0].record.finding_id);
      setStatus(
        `${newFindings.length} deeper finding${newFindings.length === 1 ? "" : "s"} available below ${formatFindingId(findingId)}. ${qualityMessage(result.analysis_quality)} The guided budget still describes the original report. Download to keep these findings with this session.`,
      );
    } catch (error) {
      try {
        const refreshed = await fetchReview(report.review_id);
        if (isReviewReport(refreshed)) {
          setReport(refreshed);
          setFindings(refreshed.findings.map(withEvidenceLabel));
        }
      } catch {
        /* Keep the last readable report. */
      }
      setStatus(error instanceof Error ? error.message : "The deeper-analysis request failed.");
    }
  }

  function exportLedger() {
    // The raw data, plus the conversation in the same shape as
    // GET /reviews/{id}/questions (ADR-0050 §10).
    downloadFile(
      `${report.review_id}-evidence-ledger.json`,
      JSON.stringify(buildReportExport({ ...report, findings }, transcript, demo), null, 2),
      "application/json",
    );
    setStatus(
      source === "fixture"
        ? "Fixture evidence ledger exported as JSON."
        : "Evidence ledger exported as JSON.",
    );
  }

  function downloadReport() {
    // One self-contained, escaped HTML file with the findings and the
    // conversation; Print → PDF works from it (ADR-0050 §10).
    downloadFile(
      `${report.review_id}-report.html`,
      buildReportHtml({ ...report, findings }, transcript, title, demo),
      "text/html",
    );
    setStatus("Report downloaded with this conversation.");
  }

  return (
    <section className="report-frame" aria-labelledby="report-heading">
      <div className="report-summary">
        <header className="report-header">
          <div>
            <span className="report-overline">{reportSourceLabels[source]}</span>
            <h1 id="report-heading">{title}</h1>
            <p>
              {report.terraform_repo_ref} ·{" "}
              {new Date(report.created_at).toLocaleString("en-US", {
                dateStyle: "medium",
                timeStyle: "short",
                timeZone: "UTC",
              })}{" "}
              UTC
            </p>
          </div>
          <div className="report-header-actions">
            <button
              className="button secondary"
              type="button"
              onClick={() =>
                document.getElementById("ask-review")?.scrollIntoView({ block: "start" })
              }
            >
              Ask questions ↓
            </button>
            <button className="button primary" type="button" onClick={downloadReport}>
              Download report
            </button>
            <button className="button secondary" type="button" onClick={exportLedger}>
              Export ledger
            </button>
            <button className="button quiet" type="button" onClick={onNewReview}>
              New review
            </button>
          </div>
        </header>
        {demo && (
          <aside className="demo-provenance" aria-label="About this demo">
            <p>
              <strong>Source:</strong>{" "}
              <a href={demo.sourceUrl} target="_blank" rel="noopener noreferrer">
                {demo.source}
              </a>{" "}
              · {demo.license}
            </p>
            <p>{demo.disclaimer}</p>
            <p>
              Every finding was checked by hand against the code.
              {reviewerNotes.size > 0
                ? ` ${reviewerNotes.size === 1 ? "One finding carries" : `${reviewerNotes.size} findings carry`} a reviewer note from that check.`
                : " The check found nothing to correct."}
            </p>
          </aside>
        )}

        <div className="report-metrics" aria-label="Report summary">
          <Metric
            label="Total findings"
            value={String(findings.length)}
            detail={
              source === "fixture"
                ? "Across the complete fixture ledger"
                : "Across the full evidence ledger"
            }
          />
          <Metric
            label="Rule results"
            value={String(ruleCount)}
            detail="Deterministic checks, not a severity count"
            emphasis
          />
          <Metric
            label="Configuration size"
            value={report.cost_estimate_tier}
            detail="Resource-count band, not a bill estimate"
          />
          <Metric
            label="Assumptions"
            value={String(assumptionCount)}
            detail="Named and versioned"
          />
        </div>
        <aside className="scope-note" aria-label="Analysis quality">
          <strong>Analysis quality</strong>
          <p>{qualityMessage(report.analysis_quality)}</p>
          {report.analysis_scope && (
            <p>
              <strong>Configuration scope. </strong>
              {scopeMessage(report.analysis_scope)}
            </p>
          )}
          {report.deeper_jobs?.map((job) => (
            <p key={job.job_id}>
              Deeper review of {formatFindingId(job.parent_finding_id)}: {job.status}.
              {job.status === "failed" && " Your original report remains available."}
            </p>
          ))}
          {report.deeper_reviews?.map((run) => (
            <p key={run.parent_finding_id}>
              Deeper review of {formatFindingId(run.parent_finding_id)}:{" "}
              {qualityMessage(run.analysis_quality)}
            </p>
          ))}
          {report.report_projection && !report.report_projection.children_available && (
            <p>Saved deeper findings are unavailable in this report configuration.</p>
          )}
          {!!report.report_projection?.excluded_child_count && (
            <p>
              Some saved deeper findings could not be included. Report completeness is limited;
              reload before relying on its totals.
            </p>
          )}
        </aside>
        {findings.some(({ record }) => record.parent_finding_id) &&
          !report.report_projection?.children_available && (
            <p className="field-help">
              The guided budget, diagram and chat context cover the original report. Added deeper
              findings are shown in the technical view and downloads.
            </p>
          )}
      </div>

      <div className="report-content">
        <div className="report-view-switch" role="tablist" aria-label="Report presentation">
          <button
            id="technical-tab"
            type="button"
            role="tab"
            aria-controls="technical-panel"
            aria-selected={view === "technical"}
            tabIndex={view === "technical" ? 0 : -1}
            onClick={() => setView("technical")}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "End") {
                event.preventDefault();
                setView("stakeholder");
                document.getElementById("stakeholder-tab")?.focus();
              }
            }}
          >
            Evidence Dashboard <span>Technical</span>
          </button>
          <button
            id="stakeholder-tab"
            type="button"
            role="tab"
            aria-controls="stakeholder-panel"
            aria-selected={view === "stakeholder"}
            tabIndex={view === "stakeholder" ? 0 : -1}
            onClick={() => setView("stakeholder")}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft" || event.key === "Home") {
                event.preventDefault();
                setView("technical");
                document.getElementById("technical-tab")?.focus();
              }
            }}
          >
            Guided Report <span>Stakeholder</span>
          </button>
        </div>

        {view === "technical" ? (
          <div id="technical-panel" role="tabpanel" aria-labelledby="technical-tab" tabIndex={0}>
            <div className="finding-filters" aria-label="Filter findings">
              {(
                [
                  "all",
                  "needed",
                  "critical",
                  "high",
                  "medium",
                  "low",
                  "none",
                  "unknown",
                ] as FindingFilter[]
              ).map((value) => (
                <button
                  className={`finding-filter-${value}`}
                  type="button"
                  key={value}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {value === "all"
                    ? `All (${findings.length})`
                    : value === "needed"
                      ? "Action proposed"
                      : value === "none"
                        ? "No action proposed"
                        : value === "unknown"
                          ? "Unassessed"
                          : `${value} risk`}
                </button>
              ))}
            </div>
            <p className="field-help">
              Risk and action assessments are separate from evidence type and confidence. Each
              assessment names its source; unassessed findings are not safety confirmations.
            </p>
            <div className="finding-toolbar">
              <label htmlFor="finding-search">
                Find findings
                <input
                  id="finding-search"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search title, category, or type"
                />
                <span className="finding-count" role="status">
                  {visibleFindings.length} {visibleFindings.length === 1 ? "finding" : "findings"}{" "}
                  shown
                </span>
              </label>
              <label htmlFor="finding-sort">
                Sort
                <select
                  id="finding-sort"
                  value={sort}
                  onChange={(event) => setSort(event.target.value as FindingSort)}
                >
                  <option value="priority">Action first, then severity</option>
                  <option value="confidence">Confidence: high to low</option>
                  <option value="title">Title: A–Z</option>
                </select>
              </label>
            </div>
            {visibleFindings.length > 0 && selected ? (
              <div
                className="evidence-workspace"
                ref={workspaceRef}
                style={
                  {
                    "--finding-navigation-width": `${100 - detailPaneWidth}fr`,
                    "--finding-detail-width": `${detailPaneWidth}fr`,
                  } as CSSProperties
                }
              >
                <ul className="finding-list" aria-label="Findings">
                  {visibleFindings.map((finding) => (
                    <li key={finding.record.finding_id}>
                      <button
                        type="button"
                        aria-current={selected.record.finding_id === finding.record.finding_id}
                        onClick={() => selectFinding(finding.record.finding_id)}
                      >
                        <span className="finding-list-main">
                          <strong>{finding.record.finding}</strong>
                          <span>
                            <AssessmentTag finding={finding} />
                            <i className="category-tag">{finding.record.category}</i>
                            <i className="type-tag">{finding.record.type}</i>
                          </span>
                        </span>
                        <span className="finding-list-score">
                          {Math.round(finding.record.confidence * 100)}%
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div
                  className="workspace-resizer"
                  role="separator"
                  aria-label="Resize finding detail"
                  aria-orientation="vertical"
                  aria-valuemin={MIN_DETAIL_PANE_WIDTH}
                  aria-valuemax={MAX_DETAIL_PANE_WIDTH}
                  aria-valuenow={Math.round(detailPaneWidth)}
                  aria-valuetext={`Finding detail uses ${Math.round(detailPaneWidth)}% of the workspace`}
                  tabIndex={0}
                  onDoubleClick={() => setDetailPaneWidth(DEFAULT_DETAIL_PANE_WIDTH)}
                  onKeyDown={handleResizeKeyDown}
                  onPointerDown={handleResizePointerDown}
                  onPointerMove={handleResizePointerMove}
                />
                <FindingDetail
                  finding={selected}
                  reviewerNote={reviewerNotes.get(selected.record.finding_id) ?? null}
                  onAsk={askAboutFinding}
                  onShowArchitecture={architecture ? showOnArchitecture : undefined}
                  onGoDeeper={goDeeper}
                />
              </div>
            ) : (
              <div className="empty-state">
                <span aria-hidden="true">⌕</span>
                <h2>No findings match</h2>
                <p>
                  Clear the search or choose another risk filter. The evidence ledger has not
                  changed.
                </p>
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => {
                    setQuery("");
                    setFilter("all");
                  }}
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>
        ) : (
          <div
            id="stakeholder-panel"
            role="tabpanel"
            aria-labelledby="stakeholder-tab"
            tabIndex={0}
          >
            <GuidedReport
              report={{ ...report, findings: report.findings.map(withEvidenceLabel) }}
              reviewerNotes={reviewerNotes}
              titled={demo !== null}
              onOpenTechnicalFinding={openTechnicalFinding}
              onAsk={askAboutFinding}
            />
          </div>
        )}

        {status && (
          <p className="action-status" role="status">
            {status}
          </p>
        )}
      </div>

      {architecture && (
        <div className="report-content">
          <ArchitectureView
            graph={architecture}
            findings={findings}
            focus={architectureFocus}
            onOpenFinding={openTechnicalFinding}
          />
        </div>
      )}

      <div className="report-content">
        <ReportQuestions
          reviewId={report.review_id}
          source={source}
          findings={findings}
          selectedFindingId={selectedId}
          questionSeed={questionSeed}
          seedFindingId={seedFindingId}
          demoChat={demoChat}
          reviewerNotes={demo?.reviewerNotes}
          onQuestionSeedConsumed={consumeQuestionSeed}
          onOpenFinding={openTechnicalFinding}
          onTranscriptChange={setTranscript}
          onDownload={downloadReport}
        />
        <div className="snapshot-bar">{reportSnapshotLabel(findings)}</div>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  emphasis = false,
}: {
  label: string;
  value: string;
  detail: string;
  emphasis?: boolean;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong className={emphasis ? "metric-emphasis" : ""}>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
