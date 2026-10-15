interface FailurePanelProps {
  message: string;
  onRetry: () => void;
  onOpenSample: () => void;
  sampleLoading: boolean;
}

export function FailurePanel({ message, onRetry, onOpenSample, sampleLoading }: FailurePanelProps) {
  return (
    <section className="flow-card state-card failure-state" aria-labelledby="failure-heading">
      <span className="state-icon" aria-hidden="true">
        !
      </span>
      <div className="step-kicker">Review could not complete</div>
      <h1 id="failure-heading">The report was not published</h1>
      <p className="lede">{message}</p>
      <div className="state-detail">
        <strong>Nothing was silently treated as complete.</strong>
        <span>
          ArchiBrief never returns a partial or simulated report as authoritative — a failed or
          incomplete run stays visibly failed until real evidence says otherwise.
        </span>
      </div>
      <div className="form-actions centered">
        <button className="button secondary" type="button" onClick={onRetry}>
          Edit submission
        </button>
        <button
          className="button primary"
          type="button"
          onClick={onOpenSample}
          disabled={sampleLoading}
        >
          {sampleLoading ? "Loading sample…" : "View the sample review"}
        </button>
      </div>
    </section>
  );
}
