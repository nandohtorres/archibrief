import { useMemo, useState } from "react";
import type { PreflightField } from "@/lib/contracts";

interface PreflightStepProps {
  initialFields: PreflightField[];
  onBack: () => void;
  onContinue: (fields: PreflightField[]) => void;
}

export function PreflightStep({ initialFields, onBack, onContinue }: PreflightStepProps) {
  const [fields, setFields] = useState(initialFields);
  const [acceptedDefaults, setAcceptedDefaults] = useState<string[]>([]);

  const requiredAnswersComplete = useMemo(
    () => fields.filter((field) => field.policy === "answer").every((field) => field.value.trim()),
    [fields],
  );
  const defaultsComplete = fields
    .filter((field) => field.policy === "default")
    .every((field) => acceptedDefaults.includes(field.id) || field.value.trim());

  function updateValue(id: string, value: string) {
    setFields((current) => current.map((field) => (field.id === id ? { ...field, value } : field)));
  }

  return (
    <section className="flow-card" aria-labelledby="preflight-heading">
      <div className="step-kicker">Baseline context · Step 2 of 3</div>
      <h1 id="preflight-heading">Resolve only what the review genuinely needs</h1>
      <p className="lede">
        ArchiBrief evaluates each missing field separately: answer it, accept a named default, or
        see why that part of the review must stop.
      </p>

      <div className="preflight-grid">
        {fields.map((field, index) => (
          <article className={`preflight-field policy-${field.policy}`} key={field.id}>
            <div className="field-heading">
              <span className="field-number">0{index + 1}</span>
              <div>
                <h2>{field.label}</h2>
                <span className={`policy-label ${field.policy}`}>
                  {field.policy === "answer"
                    ? "Answer required"
                    : field.policy === "default"
                      ? "Named default available"
                      : "Cannot safely infer"}
                </span>
              </div>
            </div>
            <p>{field.question}</p>

            {field.policy === "answer" && (
              <label className="compact-field" htmlFor={`preflight-${field.id}`}>
                Your answer
                <input
                  id={`preflight-${field.id}`}
                  value={field.value}
                  onChange={(event) => updateValue(field.id, event.target.value)}
                />
              </label>
            )}

            {field.policy === "default" && (
              <div className="default-card">
                <span>Shown default · preflight-1.2</span>
                <strong>{field.shownDefault}</strong>
                <button
                  className="button small secondary"
                  type="button"
                  aria-pressed={acceptedDefaults.includes(field.id)}
                  onClick={() =>
                    setAcceptedDefaults((current) =>
                      current.includes(field.id)
                        ? current.filter((id) => id !== field.id)
                        : [...current, field.id],
                    )
                  }
                >
                  {acceptedDefaults.includes(field.id)
                    ? "Default accepted ✓"
                    : "Accept shown default"}
                </button>
              </div>
            )}

            {field.policy === "stopped" && (
              <details className="reason-details">
                <summary>See why this portion stops</summary>
                <p>{field.reason}</p>
              </details>
            )}

            {field.policy !== "stopped" && <p className="reason-copy">Why: {field.reason}</p>}
          </article>
        ))}
      </div>

      <div className="preflight-summary">
        <strong>What the report will record</strong>
        <span>1 direct answer · 1 named assumption · 1 not-observable area</span>
      </div>
      <div className="form-actions">
        <button className="button secondary" type="button" onClick={onBack}>
          Back to submission
        </button>
        <button
          className="button primary"
          type="button"
          disabled={!requiredAnswersComplete || !defaultsComplete}
          onClick={() => onContinue(fields)}
        >
          Start fixture review
        </button>
      </div>
    </section>
  );
}
