import type { ProgressStage } from "@/lib/contracts";

interface ProgressStepProps {
  activeIndex: number;
  stages: ProgressStage[];
  onSkip: () => void;
}

export function ProgressStep({ activeIndex, stages, onSkip }: ProgressStepProps) {
  const progress = Math.min(100, Math.round(((activeIndex + 0.5) / stages.length) * 100));
  return (
    <section className="flow-card progress-card" aria-labelledby="progress-heading">
      <div className="step-kicker">Review running · Step 3 of 3</div>
      <h1 id="progress-heading">Building a reproducible evidence ledger</h1>
      <p className="lede">
        The fixture follows the real pipeline shape. Production stages pass object identifiers, not
        repository contents, through orchestration.
      </p>

      <div className="progress-meter" aria-label={`Review ${progress}% complete`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <ol className="progress-stages" aria-live="polite">
        {stages.map((stage, index) => {
          const state =
            index < activeIndex ? "complete" : index === activeIndex ? "active" : "pending";
          return (
            <li className={state} key={stage.id}>
              <span className="stage-state" aria-hidden="true">
                {state === "complete" ? "✓" : index + 1}
              </span>
              <div>
                <strong>{stage.label}</strong>
                <span>{stage.description}</span>
              </div>
              <span className="stage-label">{state === "active" ? "Running" : state}</span>
            </li>
          );
        })}
      </ol>
      <div className="progress-footer">
        <p>
          Fixture preview · approximately {Math.max(1, stages.length - activeIndex)} steps remaining
        </p>
        <button className="button secondary" type="button" onClick={onSkip}>
          View fixture report now
        </button>
      </div>
    </section>
  );
}
