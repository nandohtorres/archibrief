"use client";

import { useState } from "react";

interface ArchitectureViewProps {
  onOpenFinding: (findingId: string) => void;
}

const architectureFindings = [
  { id: "finding-001", label: "F-001 · S3 public-access protection" },
  { id: "finding-002", label: "F-002 · Lambda IAM scope" },
  { id: "finding-003", label: "F-003 · CloudTrail coverage" },
  { id: "finding-004", label: "F-004 · RDS Multi-AZ" },
];

export function ArchitectureView({ onOpenFinding }: ArchitectureViewProps) {
  const [view, setView] = useState<"submitted" | "recommended">("submitted");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [hoveredFindingId, setHoveredFindingId] = useState<string | null>(null);
  const highlightedFindingId = hoveredFindingId ?? selectedFindingId;

  return (
    <section
      className="report-section"
      id="architecture-impact"
      aria-labelledby="architecture-heading"
    >
      <div className="section-heading-row">
        <div>
          <span className="section-kicker">System context</span>
          <h2 id="architecture-heading">Architecture impact</h2>
          <p>Overlay only the changes supported by this report’s findings.</p>
        </div>
        <span className="concept-label">Preview feature</span>
      </div>

      <div
        className="architecture-shell"
        data-view={view}
        data-highlight={highlightedFindingId ?? undefined}
      >
        <div className="architecture-toolbar">
          <div className="segmented-control" role="group" aria-label="Architecture view">
            <button
              type="button"
              aria-pressed={view === "submitted"}
              onClick={() => setView("submitted")}
            >
              Submitted design
            </button>
            <button
              type="button"
              aria-pressed={view === "recommended"}
              onClick={() => setView("recommended")}
            >
              Recommended changes
            </button>
          </div>
          <p role="status">
            {view === "submitted"
              ? "Showing resources and gaps observable in submitted Terraform."
              : "Showing four bounded changes linked to report findings."}
          </p>
        </div>

        <div className="architecture-canvas">
          <svg
            className="architecture-svg"
            viewBox="0 0 1000 470"
            role="img"
            aria-labelledby="architecture-title architecture-description"
          >
            <title id="architecture-title">Payments API architecture</title>
            <desc id="architecture-description">
              Internet traffic enters API Gateway and Lambda. Lambda uses an IAM role and connects
              to an RDS database and S3 audit-log bucket. The recommended view overlays changes
              supported by four findings.
            </desc>
            <defs>
              <marker
                id="architecture-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
              </marker>
            </defs>

            <path className="diagram-edge" d="M140 220 H190" />
            <path className="diagram-edge" d="M340 220 H405" />
            <path className="diagram-edge" d="M565 205 C620 205 620 110 680 110" />
            <path className="diagram-edge" d="M565 235 C620 235 620 280 680 280" />
            <path className="diagram-edge" d="M485 355 V260" />

            <g>
              <rect className="diagram-node" x="20" y="180" width="120" height="80" />
              <text className="diagram-title" x="80" y="215">
                Internet
              </text>
              <text className="diagram-meta" x="80" y="238">
                HTTPS traffic
              </text>
            </g>
            <g>
              <rect className="diagram-node" x="190" y="180" width="150" height="80" />
              <text className="diagram-title" x="265" y="215">
                API Gateway
              </text>
              <text className="diagram-meta" x="265" y="238">
                public API
              </text>
            </g>
            <g>
              <rect className="diagram-node" x="405" y="180" width="160" height="80" />
              <text className="diagram-title" x="485" y="215">
                Payments Lambda
              </text>
              <text className="diagram-meta" x="485" y="238">
                application logic
              </text>
            </g>
            <g className="diagram-target" data-finding="finding-004">
              <rect className="diagram-node" x="680" y="70" width="180" height="80" />
              <text className="diagram-title" x="770" y="105">
                Amazon RDS
              </text>
              <text className="diagram-meta" x="770" y="128">
                payments-db
              </text>
            </g>
            <g className="diagram-target" data-finding="finding-001">
              <rect className="diagram-node" x="680" y="240" width="180" height="80" />
              <text className="diagram-title" x="770" y="275">
                Amazon S3
              </text>
              <text className="diagram-meta" x="770" y="298">
                audit-log bucket
              </text>
            </g>
            <g className="diagram-target" data-finding="finding-002">
              <rect className="diagram-node" x="405" y="355" width="160" height="80" />
              <text className="diagram-title" x="485" y="390">
                IAM role
              </text>
              <text className="diagram-meta" x="485" y="413">
                lambda-exec-payments
              </text>
            </g>

            <g className={view === "submitted" ? "" : "diagram-hidden"}>
              <rect className="diagram-marker risk" x="677" y="37" width="186" height="25" />
              <text className="diagram-marker-text risk" x="770" y="54">
                F-004 · SINGLE-AZ
              </text>
              <rect className="diagram-marker risk" x="677" y="207" width="186" height="25" />
              <text className="diagram-marker-text risk" x="770" y="224">
                F-001 · BPA NOT DECLARED
              </text>
              <rect className="diagram-marker risk" x="402" y="322" width="166" height="25" />
              <text className="diagram-marker-text risk" x="485" y="339">
                F-002 · S3:* ON *
              </text>
              <g className="diagram-target" data-finding="finding-003">
                <rect className="diagram-node missing" x="680" y="355" width="180" height="80" />
                <text className="diagram-title" x="770" y="390">
                  CloudTrail
                </text>
                <text className="diagram-meta" x="770" y="413">
                  F-003 · not observable
                </text>
              </g>
            </g>

            <g className={view === "recommended" ? "" : "diagram-hidden"}>
              <rect className="diagram-change-outline" x="680" y="70" width="180" height="80" />
              <rect className="diagram-marker change" x="677" y="37" width="186" height="25" />
              <text className="diagram-marker-text change" x="770" y="54">
                MOD · MULTI-AZ
              </text>
              <rect className="diagram-change-outline" x="680" y="240" width="180" height="80" />
              <rect className="diagram-marker change" x="677" y="207" width="186" height="25" />
              <text className="diagram-marker-text change" x="770" y="224">
                ADD · BLOCK PUBLIC ACCESS
              </text>
              <rect className="diagram-change-outline" x="405" y="355" width="160" height="80" />
              <rect className="diagram-marker change" x="402" y="322" width="166" height="25" />
              <text className="diagram-marker-text change" x="485" y="339">
                MOD · LEAST PRIVILEGE
              </text>
              <g className="diagram-target" data-finding="finding-003">
                <rect className="diagram-node added" x="680" y="355" width="180" height="80" />
                <text className="diagram-title" x="770" y="390">
                  CloudTrail
                </text>
                <text className="diagram-meta" x="770" y="413">
                  ADD · multi-Region trail
                </text>
              </g>
            </g>
          </svg>
        </div>

        <div className="diagram-legend" aria-label="Diagram legend">
          <span>
            <i className="legend-swatch" /> Submitted resource
          </span>
          <span>
            <i className="legend-swatch risk" /> Finding or evidence gap
          </span>
          <span>
            <i className="legend-swatch change" /> Finding-supported change
          </span>
        </div>
      </div>

      <div className="architecture-links" aria-label="Diagram findings">
        {architectureFindings.map((finding) => (
          <button
            type="button"
            key={finding.id}
            aria-pressed={selectedFindingId === finding.id}
            onMouseEnter={() => setHoveredFindingId(finding.id)}
            onMouseLeave={() => setHoveredFindingId(null)}
            onFocus={() => setHoveredFindingId(finding.id)}
            onBlur={() => setHoveredFindingId(null)}
            onClick={() => {
              setSelectedFindingId(finding.id);
              onOpenFinding(finding.id);
            }}
          >
            {finding.label}
            <span>Open finding ↑</span>
          </button>
        ))}
      </div>
      <p className="review-boundary">
        <strong>Boundary:</strong> This fixture visualizes submitted Terraform plus bounded,
        finding-supported changes. In-product diagram generation remains deferred past v1.
      </p>
    </section>
  );
}
