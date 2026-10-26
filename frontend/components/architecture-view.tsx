"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReportFinding, Severity } from "@/lib/contracts";
import { assessmentFor, compareAssessments } from "@/lib/assessment";
import { AssessmentTag } from "./assessment-tag";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  laneLabels,
  layoutArchitecture,
  type ArchitectureGraph,
  type PlacedNode,
} from "@/lib/architecture";
import { formatFindingId } from "@/lib/workflow";

interface ArchitectureViewProps {
  graph: ArchitectureGraph;
  findings: ReportFinding[];
  onOpenFinding: (findingId: string) => void;
  // "Show on architecture" from a finding: select the resource it sits on.
  focus?: { findingId: string; at: number } | null;
  // Shown while a review runs: the drawing only, without finding chrome.
  preview?: boolean;
}

function topPriority(findingIds: string[], byId: Map<string, ReportFinding>): Severity | "unknown" {
  let top: Severity | "unknown" = "unknown";
  const rank = { critical: 4, high: 3, medium: 2, low: 1, unknown: 0 };
  for (const id of findingIds) {
    const finding = byId.get(id);
    const severity = finding ? assessmentFor(finding).severity : null;
    if (severity && rank[severity] > rank[top]) top = severity;
  }
  return top;
}

function copiesLabel(copies: PlacedNode["copies"]): string | null {
  if (copies === undefined) return null;
  return typeof copies === "number" ? `×${copies}` : "× several";
}

function FindingButtons({
  ids,
  byId,
  onOpenFinding,
}: {
  ids: string[];
  byId: Map<string, ReportFinding>;
  onOpenFinding: (findingId: string) => void;
}) {
  const listed = ids
    .map((id) => byId.get(id))
    .filter((finding): finding is ReportFinding => finding !== undefined)
    .sort(compareAssessments);
  return (
    <ul className="architecture-finding-list">
      {listed.map((finding) => (
        <li key={finding.record.finding_id}>
          <button type="button" onClick={() => onOpenFinding(finding.record.finding_id)}>
            <AssessmentTag finding={finding} />
            <span className="architecture-finding-text">{finding.record.finding}</span>
            <span className="architecture-finding-open">
              Open {formatFindingId(finding.record.finding_id)} ↑
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ArchitectureView({
  graph,
  findings,
  onOpenFinding,
  focus,
  preview = false,
}: ArchitectureViewProps) {
  const layout = useMemo(() => layoutArchitecture(graph), [graph]);
  const byId = useMemo(
    () => new Map(findings.map((finding) => [finding.record.finding_id, finding])),
    [findings],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusedFindingId, setFocusedFindingId] = useState<string | null>(null);

  useEffect(() => {
    if (!focus) return;
    const holder = layout.nodes.find((node) => node.findings.includes(focus.findingId));
    setSelectedId(holder?.id ?? null);
    setFocusedFindingId(holder ? null : focus.findingId);
  }, [focus, layout]);

  const selected = layout.nodes.find((node) => node.id === selectedId) ?? null;
  const connected = useMemo(() => {
    if (!selectedId) return null;
    const ids = new Set([selectedId]);
    for (const edge of layout.edges) {
      if (edge.from === selectedId) ids.add(edge.to);
      if (edge.to === selectedId) ids.add(edge.from);
    }
    return ids;
  }, [layout, selectedId]);
  const names = useMemo(
    () => new Map(layout.nodes.map((node) => [node.id, `${node.label} ${node.name}`])),
    [layout],
  );
  const placedCount = layout.nodes.reduce((total, node) => total + node.findings.length, 0);

  function select(node: PlacedNode) {
    setFocusedFindingId(null);
    setSelectedId((current) => (current === node.id ? null : node.id));
  }

  return (
    <section
      className="report-section"
      id={preview ? undefined : "architecture-impact"}
      aria-labelledby={preview ? undefined : "architecture-heading"}
      aria-label={preview ? "Architecture diagram" : undefined}
    >
      {!preview && (
        <div className="section-heading-row">
          <div>
            <span className="section-kicker">System context</span>
            <h2 id="architecture-heading">Architecture</h2>
            <p>
              What the submitted Terraform creates, how its resources reference each other, and
              where each finding sits. Select a resource to see its findings.
            </p>
          </div>
          <span className="concept-label">
            {layout.nodes.length} resources · {layout.edges.length} links
          </span>
        </div>
      )}

      <div className="architecture-shell">
        <p className="diagram-swipe-hint" aria-hidden="true">
          Swipe sideways to see the whole diagram →
        </p>
        <div className="architecture-canvas">
          <div
            className="architecture-board"
            style={{ width: layout.width, height: layout.height }}
            data-selecting={selectedId ? "true" : undefined}
          >
            {layout.lanes.map(({ lane, x }) => (
              <span
                key={lane}
                className="architecture-lane-label"
                style={{ left: x, width: NODE_WIDTH }}
              >
                {laneLabels[lane]}
              </span>
            ))}
            <svg
              className="architecture-edges"
              width={layout.width}
              height={layout.height}
              aria-hidden="true"
            >
              <defs>
                <marker
                  id="architecture-arrow"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
                </marker>
              </defs>
              {layout.edges.map((edge) => (
                <path
                  key={`${edge.from}->${edge.to}`}
                  className={
                    selectedId && (edge.from === selectedId || edge.to === selectedId)
                      ? "architecture-edge active"
                      : "architecture-edge"
                  }
                  d={edge.path}
                />
              ))}
            </svg>
            {layout.nodes.map((node) => {
              const priority = topPriority(node.findings, byId);
              const copies = copiesLabel(node.copies);
              const count = node.findings.length;
              return (
                <button
                  key={node.id}
                  type="button"
                  className="architecture-node"
                  data-lane={node.lane}
                  data-dim={connected && !connected.has(node.id) ? "true" : undefined}
                  aria-pressed={selectedId === node.id}
                  aria-label={`${node.label} ${node.name}${
                    node.module ? ` in ${node.module}` : ""
                  }, ${count} finding${count === 1 ? "" : "s"}`}
                  title={node.module ? `${node.module}/${node.name}` : node.name}
                  style={{ left: node.x, top: node.y, width: NODE_WIDTH, height: NODE_HEIGHT }}
                  onClick={() => select(node)}
                >
                  <span className="architecture-node-type">
                    {node.label}
                    {copies && <em>{copies}</em>}
                  </span>
                  <strong>{node.name}</strong>
                  {node.module && <span className="architecture-node-module">{node.module}</span>}
                  {count > 0 && priority && (
                    <span className={`architecture-badge severity-${priority}`} aria-hidden="true">
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <div className="diagram-legend" aria-label="Diagram legend">
          {!preview && (
            <>
              <span>
                <i className="architecture-badge high">n</i> Rule result
              </span>
              <span>
                <i className="architecture-badge review">n</i> Needs review
              </span>
              <span>
                <i className="architecture-badge unknown">n</i> Unknown
              </span>
              <span>
                <i className="architecture-badge confirmed">n</i> Reported fact, not a safety rating
              </span>
            </>
          )}
          <span>Arrow: one resource references the other in the code</span>
        </div>
      </div>

      <div className="architecture-panel" aria-live="polite">
        {selected ? (
          <>
            <h3>
              {selected.label} · {selected.name}
              {copiesLabel(selected.copies) && <em> {copiesLabel(selected.copies)}</em>}
            </h3>
            {selected.module && <p className="architecture-meta">Module: {selected.module}</p>}
            {selected.details.length > 0 && (
              <p className="architecture-meta">Configured by: {selected.details.join(", ")}</p>
            )}
            {connected && connected.size > 1 && (
              <p className="architecture-meta">
                Linked to:{" "}
                {[...connected]
                  .filter((id) => id !== selected.id)
                  .map((id) => names.get(id))
                  .join(", ")}
              </p>
            )}
            {preview ? null : selected.findings.length > 0 ? (
              <FindingButtons ids={selected.findings} byId={byId} onOpenFinding={onOpenFinding} />
            ) : (
              <p className="architecture-meta">No findings name this resource.</p>
            )}
          </>
        ) : (
          <p className="architecture-meta">
            {preview
              ? "Select a resource to see how it's configured and what it links to."
              : placedCount > 0
                ? "Select a resource with a badge to list the findings about it."
                : "No finding names a specific resource in this review."}
          </p>
        )}
      </div>

      {!preview && graph.account_findings.length > 0 && (
        <div
          className="architecture-account"
          data-focused={
            focusedFindingId && graph.account_findings.includes(focusedFindingId)
              ? "true"
              : undefined
          }
        >
          <h3>Findings outside the diagram</h3>
          <p className="architecture-meta">
            Findings about resources omitted from this diagram, modules without exact resource
            attribution, missing configuration, or the design as a whole.
          </p>
          <FindingButtons ids={graph.account_findings} byId={byId} onOpenFinding={onOpenFinding} />
        </div>
      )}

      <p className="review-boundary">
        <strong>How this is drawn:</strong> straight from the submitted Terraform, without a model.
        Settings resources (a bucket&rsquo;s encryption block, a policy attachment) are folded into
        the resource they configure. Links are references in the code, not observed traffic.
        {graph.truncated && " This diagram shows the first 60 resources only."}
      </p>
    </section>
  );
}
