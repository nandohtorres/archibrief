import { useState, type FormEvent } from "react";

// Bundled quick-test presets (2026-10-13) — each loads a real sample
// Terraform archive (frontend/public/fixtures/*.tar, served as a static
// asset by the Next.js export) plus matching text fields, so testing the
// live pipeline doesn't require hand-building a .tar every time. Archive
// content/rule-finding counts verified directly against
// backend/lambdas/rule_engine/handler.py's real rules before being
// bundled here, not just written to look plausible — see each preset's
// comment for the exact finding count at the time it was built.
interface SubmissionPreset {
  id: string;
  label: string;
  description: string;
  fixturePath: string;
  terraformRepoRef: string;
  workloadBrief: string;
}

const submissionPresets: SubmissionPreset[] = [
  {
    id: "detailed",
    label: "Detailed (complex, cross-checked)",
    description: "12 resources across S3/RDS/IAM/Lambda/DynamoDB/EBS — 15 real findings.",
    fixturePath: "/fixtures/preset-detailed.tar",
    terraformRepoRef: "github.com/example/complex-multi-service@abc1234",
    workloadBrief:
      "Customer payments platform processing roughly 500 requests/second at peak, globally. Must meet PCI-DSS and GDPR requirements; EU customer data must stay in the EU. Requires 99.95% availability with automated multi-region failover. Financial transaction logs are retained for 7 years for regulatory audit.",
  },
  {
    id: "medium",
    label: "Medium",
    description: "6 resources, a handful of real findings — a realistic, moderately clean setup.",
    fixturePath: "/fixtures/preset-medium.tar",
    terraformRepoRef: "github.com/example/medium-analytics@def5678",
    workloadBrief:
      "Internal analytics dashboard used by roughly 20 employees during business hours. Moderate availability expectations — brief downtime is acceptable. No known regulatory constraints.",
  },
  {
    id: "loose",
    label: "Loose (minimal, sparse)",
    description: "A single under-specified resource — high violation density, almost no content.",
    fixturePath: "/fixtures/preset-loose.tar",
    terraformRepoRef: "github.com/example/loose-sandbox@9a8b7c6",
    workloadBrief:
      "Side project, still figuring out the requirements. Not sure about traffic or compliance needs yet.",
  },
];

export interface SubmissionValues {
  terraformRepoRef: string;
  workloadBrief: string;
  // Added 2026-10-12 (ADR-0045, direct-upload archive_path design) — the
  // file the client actually uploads to S3. Only required in live-API
  // mode (apiConfigured); the fixture flow never reads it, since there's
  // no real Ingest Lambda on the other end to send it to.
  archiveFile: File | null;
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
  archiveFile: null,
};

export function SubmissionStep({
  apiConfigured,
  initialValues,
  submitting,
  onSubmit,
}: SubmissionStepProps) {
  const [values, setValues] = useState(initialValues);
  const [attempted, setAttempted] = useState(false);
  const [loadingPresetId, setLoadingPresetId] = useState<string | null>(null);
  const [presetError, setPresetError] = useState<string | null>(null);
  const repoError = attempted && values.terraformRepoRef.trim().length < 5;
  const briefError = attempted && values.workloadBrief.trim().length < 40;
  const archiveError = attempted && apiConfigured && !values.archiveFile;

  async function loadPreset(preset: SubmissionPreset) {
    setLoadingPresetId(preset.id);
    setPresetError(null);
    try {
      const response = await fetch(preset.fixturePath);
      if (!response.ok) {
        throw new Error(`Could not load the bundled preset archive (HTTP ${response.status}).`);
      }
      const blob = await response.blob();
      const archiveFile = new File([blob], `${preset.id}.tar`, { type: "application/x-tar" });
      setValues({
        terraformRepoRef: preset.terraformRepoRef,
        workloadBrief: preset.workloadBrief,
        archiveFile,
      });
      setAttempted(false);
    } catch (error) {
      setPresetError(error instanceof Error ? error.message : "Could not load this preset.");
    } finally {
      setLoadingPresetId(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (
      values.terraformRepoRef.trim().length < 5 ||
      values.workloadBrief.trim().length < 40 ||
      (apiConfigured && !values.archiveFile)
    ) {
      return;
    }
    await onSubmit(values);
  }

  return (
    <section className="flow-card submission-card" aria-labelledby="submission-heading">
      <div className="step-kicker">Review your own Terraform · Step 1 of 3</div>
      <h2 id="submission-heading">Review an existing AWS architecture</h2>
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

      {apiConfigured && (
        <div className="preset-grid" role="group" aria-label="Quick-test presets">
          {submissionPresets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="button small secondary preset-button"
              disabled={loadingPresetId !== null}
              onClick={() => loadPreset(preset)}
            >
              <strong>{loadingPresetId === preset.id ? "Loading…" : preset.label}</strong>
              <span>{preset.description}</span>
            </button>
          ))}
        </div>
      )}
      {presetError && (
        <p className="field-error" role="alert">
          {presetError}
        </p>
      )}

      <form className="submission-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="terraform-ref">
          Terraform repository reference
          <span>Repository URL or immutable commit reference (label only)</span>
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
          A label for your report only — ArchiBrief reviews the archive you upload below, not this
          link.
        </div>
        {repoError && (
          <div id="terraform-ref-error" className="field-error" role="alert">
            Enter a repository or immutable Terraform reference.
          </div>
        )}

        <label htmlFor="terraform-archive">
          Terraform archive
          <span>A .tar/.tar.gz of the configuration to review (max 20 MB)</span>
        </label>
        <input
          id="terraform-archive"
          name="archiveFile"
          type="file"
          accept=".tar,.tar.gz,.tgz"
          aria-invalid={archiveError}
          aria-describedby={archiveError ? "terraform-archive-error" : "terraform-archive-help"}
          onChange={(event) =>
            setValues({ ...values, archiveFile: event.target.files?.[0] ?? null })
          }
        />
        <div id="terraform-archive-help" className="field-help">
          {apiConfigured
            ? "Uploaded directly to storage via a presigned URL — never routed through this API."
            : "Only required against a deployed API. The fixture flow below doesn't need a real archive."}
        </div>
        {archiveError && (
          <div id="terraform-archive-error" className="field-error" role="alert">
            Select a Terraform archive to submit.
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
