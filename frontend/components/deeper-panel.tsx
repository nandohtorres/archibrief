"use client";

import { useEffect, useRef, useState } from "react";
import { qualityMessage } from "@/lib/analysis-quality";
import type { AnalysisQuality, ReportFinding } from "@/lib/contracts";
import { AssessmentTag } from "./assessment-tag";

// What a finding's "Go deeper" run looks like right now, derived from the
// saved report (deeper_jobs, deeper_reviews and child findings).
export type DeeperPanelState =
  | { kind: "running"; startedAt: number }
  | { kind: "complete"; children: ReportFinding[]; quality?: AnalysisQuality }
  | { kind: "failed"; failureCode?: string | null };

interface DeeperPanelProps {
  state: DeeperPanelState;
  onOpenFinding: (findingId: string) => void;
}

function elapsed(startedAt: number, now: number): string {
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function failureText(code?: string | null): string {
  if (code === "timed_out") return "It ran out of time before finishing.";
  if (code === "paused") return "New analysis is paused right now.";
  return "The analysis didn't produce a usable result.";
}

export function DeeperPanel({ state, onOpenFinding }: DeeperPanelProps) {
  const [now, setNow] = useState(() => Date.now());
  // The panel sits below a long finding: bring it into view when a run
  // starts and when it ends, but not when revisiting a finished run.
  const panel = useRef<HTMLElement>(null);
  const shownKind = useRef<DeeperPanelState["kind"] | null>(null);
  useEffect(() => {
    const previous = shownKind.current;
    shownKind.current = state.kind;
    if (state.kind === "running" ? previous !== "running" : previous === "running")
      panel.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [state.kind]);
  useEffect(() => {
    if (state.kind !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [state.kind]);

  if (state.kind === "running") {
    return (
      <section
        ref={panel}
        className="deeper-panel running"
        aria-live="polite"
        aria-label="Deeper analysis"
      >
        <div className="deeper-panel-heading">
          <h4>Deeper analysis running</h4>
          <span className="deeper-elapsed">{elapsed(state.startedAt, now)}</span>
        </div>
        <div className="deeper-progress" aria-hidden="true">
          <i />
        </div>
        <p>
          Digging into this finding. This usually takes about a minute; you can keep using the
          report meanwhile.
        </p>
      </section>
    );
  }

  if (state.kind === "failed") {
    return (
      <section
        ref={panel}
        className="deeper-panel failed"
        aria-live="polite"
        aria-label="Deeper analysis"
      >
        <h4>Deeper analysis could not finish</h4>
        <p>{failureText(state.failureCode)} The original finding is unchanged.</p>
      </section>
    );
  }

  const count = state.children.length;
  return (
    <details
      ref={panel as React.RefObject<HTMLDetailsElement>}
      className="deeper-panel complete"
      open
      aria-label="Deeper analysis"
    >
      <summary>
        <h4>Deeper analysis</h4>
        <span className="deeper-summary">
          {count === 0
            ? "No additional issues found"
            : `${count} new finding${count === 1 ? "" : "s"}`}
        </span>
      </summary>
      {count > 0 && (
        <ul className="deeper-children">
          {state.children.map((child) => (
            <li key={child.record.finding_id}>
              <div className="deeper-child-heading">
                <AssessmentTag finding={child} />
                <strong>{child.record.finding}</strong>
              </div>
              <p>{child.record.recommendation}</p>
              <button
                className="button secondary deeper-open"
                type="button"
                onClick={() => onOpenFinding(child.record.finding_id)}
              >
                Open full finding
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="deeper-quality">{qualityMessage(state.quality)}</p>
    </details>
  );
}
