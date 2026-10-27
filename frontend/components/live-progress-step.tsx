import type { ArchitectureGraph } from "@/lib/architecture";
import { describeProgress } from "@/lib/progress";
import { ArchitectureView } from "./architecture-view";
import { LoadingFacts } from "./loading-facts";

interface LiveProgressStepProps {
  // False while the archive is still uploading and the review doesn't exist yet.
  started: boolean;
  currentStage: string | null;
  elapsedSeconds: number;
  // The diagram RuleEngine built, available before the model finishes.
  architecture: ArchitectureGraph | null;
  onCancel: () => void;
}

// describeProgress() (lib/progress.ts) maps the pipeline's real
// "currentStage" to a few generic steps; internal stage names stay internal.
export function LiveProgressStep({
  started,
  currentStage,
  elapsedSeconds,
  architecture,
  onCancel,
}: LiveProgressStepProps) {
  const progress = describeProgress(currentStage);

  return (
    <section className="flow-card progress-card" aria-labelledby="live-progress-heading">
      <div className="step-kicker">
        Step {progress.stageIndex} of {progress.totalStages}
      </div>
      <h1 id="live-progress-heading">{progress.macroLabel}</h1>
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
        {progress.microLabel}
        {started && ` · ${elapsedSeconds}s`}
      </p>
      <LoadingFacts />
      {architecture && (
        <div className="progress-architecture" aria-label="Your architecture">
          <h2>Your architecture</h2>
          <p>Mapped from your code. Findings appear on it when the review finishes.</p>
          <ArchitectureView
            graph={architecture}
            findings={[]}
            onOpenFinding={() => undefined}
            preview
          />
        </div>
      )}
      {started && (
        <div className="progress-footer">
          <button className="button secondary" type="button" onClick={onCancel}>
            Back to home
          </button>
          <p>
            The review keeps running. Reopen it from &ldquo;Previous Reviews&rdquo; on the home
            page.
          </p>
        </div>
      )}
    </section>
  );
}
