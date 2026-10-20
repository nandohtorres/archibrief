import { useState } from "react";

interface ClarifyStepProps {
  reviewId: string;
  fields: string[];
  submitting: boolean;
  error: string | null;
  onSubmit: (answers: Record<string, string>, additionalNotes: string) => void;
  onCancel: () => void;
}

interface YesNoMultiSelectSchema {
  kind: "yes_no_multiselect";
  label: string;
  question: string;
  options: string[];
}

interface TextSchema {
  kind: "text";
  label: string;
  question: string;
}

type FieldSchema = YesNoMultiSelectSchema | TextSchema;

// Known baseline-field schemas — mirrors backend/agent/nodes/
// preflight.py's FIELD_LABELS, extended with the actual question text
// and answer shape (yes/no + multi-select, rather than a bare free-text
// box). Falls back to a plain free-text
// field for anything not listed here, so an unrecognized field still
// renders something usable instead of breaking the form.
const FIELD_SCHEMAS: Record<string, YesNoMultiSelectSchema> = {
  regulatory_data_residency: {
    kind: "yes_no_multiselect",
    label: "Regulatory and data residency",
    question:
      "Does this workload have a specific data residency or regulatory requirement? ArchiBrief cannot safely assume an answer here.",
    options: ["GDPR", "HIPAA", "PCI-DSS", "CCPA", "Other"],
  },
};

function schemaFor(field: string): FieldSchema {
  const known = FIELD_SCHEMAS[field];
  if (known) return known;
  const label = field
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
  return { kind: "text", label, question: `Please provide an answer for "${label}".` };
}

type YesNoMultiSelectAnswer = {
  kind: "yes_no_multiselect";
  yesNo: "yes" | "no" | null;
  selected: string[];
};
type TextAnswer = { kind: "text"; value: string };
type FieldAnswer = YesNoMultiSelectAnswer | TextAnswer;

function composeAnswer(answer: FieldAnswer): string | null {
  if (answer.kind === "text") {
    const trimmed = answer.value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (answer.yesNo === "no") return "No — no regulatory or data residency requirement specified.";
  if (answer.yesNo === "yes" && answer.selected.length > 0) {
    return `Yes — applicable: ${answer.selected.join(", ")}`;
  }
  return null;
}

export function ClarifyStep({
  reviewId,
  fields,
  submitting,
  error,
  onSubmit,
  onCancel,
}: ClarifyStepProps) {
  const [fieldAnswers, setFieldAnswers] = useState<Record<string, FieldAnswer>>({});
  const [additionalNotes, setAdditionalNotes] = useState("");

  function answerFor(field: string): FieldAnswer {
    const existing = fieldAnswers[field];
    if (existing) return existing;
    const schema = schemaFor(field);
    return schema.kind === "yes_no_multiselect"
      ? { kind: "yes_no_multiselect", yesNo: null, selected: [] }
      : { kind: "text", value: "" };
  }

  function setYesNo(field: string, yesNo: "yes" | "no") {
    setFieldAnswers((current) => ({
      ...current,
      [field]: {
        kind: "yes_no_multiselect",
        yesNo,
        selected:
          yesNo === "no"
            ? []
            : ((current[field] as YesNoMultiSelectAnswer | undefined)?.selected ?? []),
      },
    }));
  }

  function toggleOption(field: string, option: string) {
    setFieldAnswers((current) => {
      const existing = (current[field] as YesNoMultiSelectAnswer | undefined) ?? {
        kind: "yes_no_multiselect",
        yesNo: "yes",
        selected: [],
      };
      const selected = existing.selected.includes(option)
        ? existing.selected.filter((item) => item !== option)
        : [...existing.selected, option];
      return { ...current, [field]: { ...existing, selected } };
    });
  }

  function setTextValue(field: string, value: string) {
    setFieldAnswers((current) => ({ ...current, [field]: { kind: "text", value } }));
  }

  const composedAnswers: Record<string, string | null> = {};
  for (const field of fields) {
    composedAnswers[field] = composeAnswer(answerFor(field));
  }
  const allAnswered = fields.every((field) => composedAnswers[field] !== null);

  function handleSubmit() {
    const answers: Record<string, string> = {};
    for (const field of fields) {
      const value = composedAnswers[field];
      if (value) answers[field] = value;
    }
    onSubmit(answers, additionalNotes.trim());
  }

  return (
    <section className="flow-card" aria-labelledby="clarify-heading">
      <div className="step-kicker">Clarification needed · review paused</div>
      <h1 id="clarify-heading">ArchiBrief needs more information to continue</h1>
      <p className="lede">
        Review <code>{reviewId}</code> is still running — Step Functions is paused at this exact
        point and will resume as soon as this is answered. Nothing has failed.
      </p>

      <div className="preflight-grid">
        {fields.map((field, index) => {
          const schema = schemaFor(field);
          const answer = answerFor(field);
          return (
            <article className="preflight-field policy-answer" key={field}>
              <div className="field-heading">
                <span className="field-number">0{index + 1}</span>
                <div>
                  <h2>{schema.label}</h2>
                  <span className="policy-label answer">Answer required</span>
                </div>
              </div>
              <p>{schema.question}</p>

              {schema.kind === "yes_no_multiselect" && answer.kind === "yes_no_multiselect" && (
                <>
                  <div
                    className="yes-no-toggle"
                    role="group"
                    aria-label={`${schema.label} — yes or no`}
                  >
                    <button
                      type="button"
                      className={`button small ${answer.yesNo === "yes" ? "primary" : "secondary"}`}
                      aria-pressed={answer.yesNo === "yes"}
                      disabled={submitting}
                      onClick={() => setYesNo(field, "yes")}
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      className={`button small ${answer.yesNo === "no" ? "primary" : "secondary"}`}
                      aria-pressed={answer.yesNo === "no"}
                      disabled={submitting}
                      onClick={() => setYesNo(field, "no")}
                    >
                      No
                    </button>
                  </div>
                  {answer.yesNo === "yes" && (
                    <div className="multiselect-options" role="group" aria-label="Which apply">
                      {schema.options.map((option) => (
                        <label key={option} className="multiselect-option">
                          <input
                            type="checkbox"
                            checked={answer.selected.includes(option)}
                            disabled={submitting}
                            onChange={() => toggleOption(field, option)}
                          />
                          {option}
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}

              {schema.kind === "text" && answer.kind === "text" && (
                <label className="compact-field" htmlFor={`clarify-${field}`}>
                  Your answer
                  <input
                    id={`clarify-${field}`}
                    value={answer.value}
                    onChange={(event) => setTextValue(field, event.target.value)}
                    disabled={submitting}
                  />
                </label>
              )}
            </article>
          );
        })}
      </div>

      <label className="compact-field" htmlFor="clarify-additional-notes">
        Anything else to take into consideration? (optional)
        <textarea
          id="clarify-additional-notes"
          rows={3}
          value={additionalNotes}
          onChange={(event) => setAdditionalNotes(event.target.value)}
          disabled={submitting}
          placeholder="Any extra context not covered above…"
        />
      </label>

      {error && (
        <p className="lede" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button className="button secondary" type="button" onClick={onCancel} disabled={submitting}>
          Cancel and return to submission
        </button>
        <button
          className="button primary"
          type="button"
          disabled={!allAnswered || submitting}
          onClick={handleSubmit}
        >
          {submitting ? "Submitting..." : "Submit answer and resume review"}
        </button>
      </div>
    </section>
  );
}
