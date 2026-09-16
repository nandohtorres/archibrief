import { useState, type FormEvent } from "react";

export interface SubmissionValues {
  terraformRepoRef: string;
  workloadBrief: string;
}

interface SubmissionStepProps {
  apiConfigured: boolean;
  initialValues: SubmissionValues;
  submitting: boolean;
  onSubmit: (values: SubmissionValues) => Promise<void>;
}

const fixtureValues: SubmissionValues = {
  terraformRepoRef: "github.com/example/payments-api@a91f3c2",
  workloadBrief:
    "A customer-facing payments API running about 40 requests/second at peak. Transaction audit logs must be retained. Target availability is 99.9%; brief interruptions are tolerable. Regulatory and data-residency requirements are not yet confirmed.",
};

export function SubmissionStep({
  apiConfigured,
  initialValues,
  submitting,
  onSubmit,
}: SubmissionStepProps) {
  const [values, setValues] = useState(initialValues);
  const [attempted, setAttempted] = useState(false);
  const repoError = attempted && values.terraformRepoRef.trim().length < 5;
  const briefError = attempted && values.workloadBrief.trim().length < 40;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (values.terraformRepoRef.trim().length < 5 || values.workloadBrief.trim().length < 40) {
      return;
    }
    await onSubmit(values);
  }

  return (
    <section className="flow-card submission-card" aria-labelledby="submission-heading">
      <div className="step-kicker">New review · Step 1 of 3</div>
      <h1 id="submission-heading">Review an existing AWS architecture</h1>
      <p className="lede">
        Submit a bounded Terraform reference and a workload brief. ArchiBrief statically reviews the
        code—it never runs Terraform or accesses your live AWS account.
      </p>

      <div className="boundary-callout">
        <strong>Before you submit</strong>
        <span>
          Remove secrets and customer data. Remote-module internals remain not observable unless
          separately allowlisted.
        </span>
      </div>

      <form className="submission-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="terraform-ref">
          Terraform repository reference
          <span>Repository URL or immutable commit reference</span>
        </label>
        <input
          id="terraform-ref"
          name="terraformRepoRef"
          value={values.terraformRepoRef}
          aria-invalid={repoError}
          aria-describedby={repoError ? "terraform-ref-error" : "terraform-ref-help"}
          onChange={(event) => setValues({ ...values, terraformRepoRef: event.target.value })}
          placeholder="github.com/organization/repository@commit"
        />
        <div id="terraform-ref-help" className="field-help">
          The current API contract accepts a reference; upload support is not represented here.
        </div>
        {repoError && (
          <div id="terraform-ref-error" className="field-error" role="alert">
            Enter a repository or immutable Terraform reference.
          </div>
        )}

        <label htmlFor="workload-brief">
          Workload brief
          <span>Purpose, traffic, availability, data sensitivity, and known constraints</span>
        </label>
        <textarea
          id="workload-brief"
          name="workloadBrief"
          rows={7}
          value={values.workloadBrief}
          aria-invalid={briefError}
          aria-describedby={briefError ? "workload-brief-error" : "workload-brief-help"}
          onChange={(event) => setValues({ ...values, workloadBrief: event.target.value })}
          placeholder="Describe what the system does and the constraints the review should evaluate…"
        />
        <div id="workload-brief-help" className="field-help">
          At least a few sentences prevents the model from inventing missing business context.
        </div>
        {briefError && (
          <div id="workload-brief-error" className="field-error" role="alert">
            Add at least 40 characters of workload context.
          </div>
        )}

        <div className="form-actions">
          <button
            className="button secondary"
            type="button"
            onClick={() => {
              setValues(fixtureValues);
              setAttempted(false);
            }}
          >
            Load reference fixture
          </button>
          <button className="button primary" type="submit" disabled={submitting}>
            {submitting
              ? "Submitting…"
              : apiConfigured
                ? "Submit to deployed API"
                : "Continue with fixture"}
          </button>
        </div>
      </form>
    </section>
  );
}
