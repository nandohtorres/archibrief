import { describeProgress } from "@/lib/progress";

interface LiveProgressStepProps {
  reviewId: string;
  currentStage: string | null;
  elapsedSeconds: number;
  onCancel: () => void;
}

// Deliberately NOT the raw internal pipeline status — this project's own
// stage names (Ingest/RuleEngine/InvokeAgent/...) stay internal.
// describeProgress() (lib/progress.ts) maps the real "currentStage"
// value, written directly by the pipeline's RecordStage* Step Functions
// states, to a small set of generic macro-stage labels plus a friendlier
// micro-step description and a percent-complete figure. Still honest
// about being real, polled status (not a simulated fixture) — just
// abstracted rather than exposing internal structure.
export function LiveProgressStep({
  reviewId,
  currentStage,
  elapsedSeconds,
  onCancel,
}: LiveProgressStepProps) {
  const progress = describeProgress(currentStage);

  return (
    <section className="flow-card progress-card" aria-labelledby="live-progress-heading">
      <div className="step-kicker">
        Review running · Step {progress.stageIndex} of {progress.totalStages}
      </div>
      <h1 id="live-progress-heading">{progress.macroLabel}</h1>
      <p className="lede">
        Review <code>{reviewId}</code> was accepted and is running. This polls{" "}
        <code>GET /reviews/{"{reviewId}"}</code> for its real status — nothing here is simulated.
      </p>
      <div
        className="progress-bar-track"
        role="progressbar"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Review progress"
      >
        <div className="progress-bar-fill" style={{ width: `${progress.percent}%` }} />
      </div>
      <p aria-live="polite">
        {progress.microLabel} · {progress.percent}% · waiting {elapsedSeconds}s
      </p>
      <div className="progress-footer">
        <button className="button secondary" type="button" onClick={onCancel}>
          Cancel and return to submission
        </button>
      </div>
    </section>
  );
}
