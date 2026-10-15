"use client";

import {
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import type { ReportFinding, ReviewReport } from "@/lib/contracts";
import { getApiBaseUrl, requestDeeperFinding } from "@/lib/api";
import {
  filterAndSortFindings,
  formatFindingId,
  type FindingFilter,
  type FindingSort,
} from "@/lib/workflow";
import { ArchitectureView } from "./architecture-view";
import { FindingDetail } from "./finding-detail";
import { GuidedReport } from "./guided-report";
import { ReportQuestions } from "./report-questions";

interface ReportWorkspaceProps {
  report: ReviewReport;
  adminKey: string;
  onNewReview: () => void;
}

const DEFAULT_DETAIL_PANE_WIDTH = 75;
const MIN_DETAIL_PANE_WIDTH = 45;
const MAX_DETAIL_PANE_WIDTH = 85;

export function ReportWorkspace({ report, adminKey, onNewReview }: ReportWorkspaceProps) {
  const [view, setView] = useState<"technical" | "stakeholder">("technical");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FindingFilter>("all");
  const [sort, setSort] = useState<FindingSort>("priority");
  const [findings, setFindings] = useState<ReportFinding[]>(report.findings);
  const [selectedId, setSelectedId] = useState(report.findings[0]?.record.finding_id ?? "");
  const [status, setStatus] = useState("");
  const [questionSeed, setQuestionSeed] = useState("");
  const [detailPaneWidth, setDetailPaneWidth] = useState(DEFAULT_DETAIL_PANE_WIDTH);
  const workspaceRef = useRef<HTMLDivElement>(null);

  const visibleFindings = useMemo(
    () => filterAndSortFindings(findings, query, filter, sort),
    [findings, query, filter, sort],
  );
  const selected =
    visibleFindings.find(({ record }) => record.finding_id === selectedId) ?? visibleFindings[0];
  const highCount = findings.filter(({ presentation }) => presentation.priority === "high").length;
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
    setQuestionSeed(
      `Explain ${formatFindingId(finding.record.finding_id)}: ${finding.record.finding}`,
    );
    window.requestAnimationFrame(() =>
      document.getElementById("ask-review")?.scrollIntoView({ block: "start" }),
    );
  }

  function showOnArchitecture(findingId: string) {
    setStatus(`${formatFindingId(findingId)} is represented in the architecture-impact section.`);
    document.getElementById("architecture-impact")?.scrollIntoView({ block: "start" });
  }

  async function goDeeper(findingId: string) {
    if (!getApiBaseUrl()) {
      setStatus(
        `Fixture only: ${formatFindingId(findingId)} would create a versioned child finding. The endpoint is not deployed.`,
      );
      return;
    }
    try {
      const result = (await requestDeeperFinding(report.review_id, findingId, adminKey)) as {
        findings: ReportFinding[];
      };
      const newFindings = result.findings ?? [];
      if (newFindings.length === 0) {
        setStatus(`The deeper request for ${formatFindingId(findingId)} returned no new findings.`);
        return;
      }
      setFindings((current) => [...current, ...newFindings]);
      selectFinding(newFindings[0].record.finding_id);
      setStatus(
        `${newFindings.length} deeper finding${newFindings.length === 1 ? "" : "s"} added below ${formatFindingId(findingId)}.`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "The deeper-analysis request failed.");
    }
  }

  function exportLedger() {
    const blob = new Blob([JSON.stringify({ ...report, findings }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.review_id}-evidence-ledger.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Fixture evidence ledger exported as JSON.");
  }

  return (
    <section className="report-frame" aria-labelledby="report-heading">
      <div className="report-summary">
        <header className="report-header">
          <div>
            <span className="report-overline">Complete · fixture evidence ledger</span>
            <h1 id="report-heading">payments-api architecture review</h1>
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
            <button className="button primary" type="button" onClick={exportLedger}>
              Export ledger
            </button>
            <button className="button quiet" type="button" onClick={onNewReview}>
              New review
            </button>
          </div>
        </header>

        <div className="report-metrics" aria-label="Report summary">
          <Metric
            label="Total findings"
            value={String(findings.length)}
            detail="Across the complete fixture ledger"
          />
          <Metric
            label="Needs action"
            value={String(highCount)}
            detail="High-risk findings to validate"
            emphasis
          />
          <Metric
            label="Cost tier"
            value={report.cost_estimate_tier}
            detail="Not a dollar forecast"
          />
          <Metric
            label="Assumptions"
            value={String(assumptionCount)}
            detail="Named and versioned"
          />
        </div>
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
              {(["all", "high", "review", "confirmed", "unknown"] as FindingFilter[]).map(
                (value) => (
                  <button
                    className={`finding-filter-${value}`}
                    type="button"
                    key={value}
                    aria-pressed={filter === value}
                    onClick={() => setFilter(value)}
                  >
                    {value === "all" ? `All (${findings.length})` : value}
                  </button>
                ),
              )}
            </div>
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
                  <option value="priority">Risk: high to low</option>
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
                            <i className={`priority-pill ${finding.presentation.priority}`}>
                              {finding.presentation.short_label}
                            </i>
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
                  onAsk={askAboutFinding}
                  onShowArchitecture={showOnArchitecture}
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
              report={report}
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

      <div className="report-content">
        <ArchitectureView onOpenFinding={openTechnicalFinding} />
      </div>

      <div className="report-content">
        <ReportQuestions
          findings={findings}
          selectedFindingId={selectedId}
          questionSeed={questionSeed}
          onQuestionSeedConsumed={() => setQuestionSeed("")}
          onOpenFinding={openTechnicalFinding}
        />
        <div className="snapshot-bar">
          Snapshot · rules 2026.09.1 · corpus 2026-09-06 · prompt 1.4 where used · static review
          only
        </div>
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
