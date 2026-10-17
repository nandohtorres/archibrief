import { useState, type FormEvent, type ReactNode } from "react";

import { createTar } from "@/lib/tar";

// The "try it" section of the landing page (2026-10-15): where the story
// turns into the product. Reuses the original testing form, plus:
// - pre-made example architectures in plain words (Fernando: pre-made, not
//   generated live), each a real bundled Terraform archive;
// - upload a .tar, or paste Terraform (turned into a .tar in the browser,
//   lib/tar.ts, so it takes the same upload + ingest path);
// - the admin key next to the submit button. Submitting stays owner-only
//   until public submissions open (ADR-0046/0047).

// Bundled examples (2026-10-13): each loads a real Terraform archive
// (frontend/public/fixtures/*.tar) plus a matching brief. Finding counts
// were verified against the real rule engine when they were built.
interface ExampleArchitecture {
  id: string;
  label: string;
  size: string;
  description: string;
  fixturePath: string;
  terraformRepoRef: string;
  workloadBrief: string;
}

const examples: ExampleArchitecture[] = [
  {
    id: "detailed",
    label: "Payments platform",
    size: "Complex · 12 resources",
    description: "Global payments with PCI-DSS and GDPR needs and a 99.95% availability target.",
    fixturePath: "/fixtures/preset-detailed.tar",
    terraformRepoRef: "github.com/example/complex-multi-service@abc1234",
    workloadBrief:
      "Customer payments platform processing roughly 500 requests/second at peak, globally. Must meet PCI-DSS and GDPR requirements; EU customer data must stay in the EU. Requires 99.95% availability with automated multi-region failover. Financial transaction logs are retained for 7 years for regulatory audit.",
  },
  {
    id: "medium",
    label: "Internal analytics dashboard",
    size: "Medium · 6 resources",
    description: "A business-hours tool for about 20 employees. Brief downtime is fine.",
    fixturePath: "/fixtures/preset-medium.tar",
    terraformRepoRef: "github.com/example/medium-analytics@def5678",
    workloadBrief:
      "Internal analytics dashboard used by roughly 20 employees during business hours. Moderate availability expectations — brief downtime is acceptable. No known regulatory constraints.",
  },
  {
    id: "loose",
    label: "Side project",
    size: "Minimal · 1 resource",
    description: "An early project with unclear requirements and very little configuration.",
    fixturePath: "/fixtures/preset-loose.tar",
    terraformRepoRef: "github.com/example/loose-sandbox@9a8b7c6",
    workloadBrief:
      "Side project, still figuring out the requirements. Not sure about traffic or compliance needs yet.",
  },
];

export interface SubmissionValues {
  terraformRepoRef: string;
  workloadBrief: string;
  // The archive the client uploads to S3 (ADR-0045). Only required in
  // live-API mode; the fixture flow never reads it. Pasted Terraform is
  // turned into this archive on submit.
  archiveFile: File | null;
}

type Source = "upload" | "paste";

// A pasted config this large is better uploaded as an archive.
export const MAX_PASTE_BYTES = 200 * 1024;

interface SubmissionStepProps {
  apiConfigured: boolean;
  initialValues: SubmissionValues;
  submitting: boolean;
  // Shown under the submit button, e.g. while submissions are owner-only.
  notice?: string | null;
  adminKey: string;
  onAdminKeyChange: (value: string) => void;
  onSubmit: (values: SubmissionValues) => Promise<void>;
  // Finished demo reviews, shown above the example architectures.
  demos?: ReactNode;
}

const fixtureValues: SubmissionValues = {
  terraformRepoRef: "github.com/example/payments-api@a91f3c2",
  workloadBrief:
    "A customer-facing payments API running about 40 requests/second at peak. Transaction audit logs must be retained. Target availability is 99.9%; brief interruptions are tolerable. Regulatory and data-residency requirements are not yet confirmed.",
  archiveFile: null,
};

export function pastedArchive(terraform: string): File {
  const tar = createTar([{ name: "main.tf", content: terraform }]);
  return new File([tar], "pasted-terraform.tar", { type: "application/x-tar" });
}

export function SubmissionStep({
  apiConfigured,
  initialValues,
  submitting,
  notice = null,
  adminKey,
  onAdminKeyChange,
  onSubmit,
  demos = null,
}: SubmissionStepProps) {
  const [values, setValues] = useState(initialValues);
  const [source, setSource] = useState<Source>("upload");
  const [pasted, setPasted] = useState("");
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [loadingExampleId, setLoadingExampleId] = useState<string | null>(null);
  const [exampleError, setExampleError] = useState<string | null>(null);

  const pastedBytes = new TextEncoder().encode(pasted).length;
  const repoError = attempted && values.terraformRepoRef.trim().length < 5;
  const briefError = attempted && values.workloadBrief.trim().length < 40;
  const archiveError = attempted && apiConfigured && source === "upload" && !values.archiveFile;
  const pasteError =
    attempted &&
    apiConfigured &&
    source === "paste" &&
    (pasted.trim().length < 20 || pastedBytes > MAX_PASTE_BYTES);
  const loadedExample = examples.find((example) => example.id === exampleId);

  async function loadExample(example: ExampleArchitecture) {
    setLoadingExampleId(example.id);
    setExampleError(null);
    try {
      const response = await fetch(example.fixturePath);
      if (!response.ok) {
        throw new Error(`Could not load the example archive (HTTP ${response.status}).`);
      }
      const blob = await response.blob();
      const archiveFile = new File([blob], `${example.id}.tar`, { type: "application/x-tar" });
      setValues({
        terraformRepoRef: example.terraformRepoRef,
        workloadBrief: example.workloadBrief,
        archiveFile,
      });
      setSource("upload");
      setExampleId(example.id);
      setAttempted(false);
    } catch (error) {
      setExampleError(error instanceof Error ? error.message : "Could not load this example.");
    } finally {
      setLoadingExampleId(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (values.terraformRepoRef.trim().length < 5 || values.workloadBrief.trim().length < 40) {
      return;
    }
    if (!apiConfigured) {
      await onSubmit(values);
      return;
    }
    if (source === "paste") {
      if (pasted.trim().length < 20 || pastedBytes > MAX_PASTE_BYTES) return;
      await onSubmit({ ...values, archiveFile: pastedArchive(pasted) });
      return;
    }
    if (!values.archiveFile) return;
    await onSubmit(values);
  }

  return (
    <section className="flow-card submission-card" aria-labelledby="submission-heading">
      <div className="step-kicker">Try it · Step 1 of 3</div>
      <h2 id="submission-heading">Review your own Terraform</h2>
      <p className="lede">
        Upload or paste your Terraform, or start from an example architecture, and add a short brief
        about the workload. ArchiBrief reads the code; it never runs Terraform or touches your AWS
        account.
      </p>

      <div className="boundary-callout">
        <strong>Before you submit</strong>
        <span>
          Remove secrets and customer data. Modules pulled from elsewhere aren&apos;t reviewed; they
          show up as gaps.
        </span>
      </div>

      {demos}

      {apiConfigured && (
        <>
          <h3 className="example-heading" id="examples-heading">
            Start from an example architecture
          </h3>
          <div className="preset-grid" role="group" aria-labelledby="examples-heading">
            {examples.map((example) => (
              <button
                key={example.id}
                type="button"
                className={`button small secondary preset-button${exampleId === example.id ? " selected" : ""}`}
                aria-pressed={exampleId === example.id}
                disabled={loadingExampleId !== null}
                onClick={() => loadExample(example)}
              >
                <strong>{loadingExampleId === example.id ? "Loading…" : example.label}</strong>
                <small>{example.size}</small>
                <span>{example.description}</span>
              </button>
            ))}
          </div>
        </>
      )}
      {exampleError && (
        <p className="field-error" role="alert">
          {exampleError}
        </p>
      )}

      <form className="submission-form" onSubmit={handleSubmit} noValidate>
        {apiConfigured && (
          <fieldset className="source-toggle">
            <legend>Your Terraform</legend>
            <label>
              <input
                type="radio"
                name="source"
                value="upload"
                checked={source === "upload"}
                onChange={() => setSource("upload")}
              />
              Upload an archive
            </label>
            <label>
              <input
                type="radio"
                name="source"
                value="paste"
                checked={source === "paste"}
                onChange={() => {
                  setSource("paste");
                  setExampleId(null);
                }}
              />
              Paste Terraform
            </label>
          </fieldset>
        )}

        {source === "upload" ? (
          <>
            <label htmlFor="terraform-archive">
              Terraform archive
              <span>A .tar or .tar.gz of the configuration to review (max 20 MB)</span>
            </label>
            <input
              id="terraform-archive"
              name="archiveFile"
              type="file"
              accept=".tar,.tar.gz,.tgz"
              aria-invalid={archiveError}
              aria-describedby={archiveError ? "terraform-archive-error" : "terraform-archive-help"}
              onChange={(event) => {
                setValues({ ...values, archiveFile: event.target.files?.[0] ?? null });
                setExampleId(null);
              }}
            />
            <div id="terraform-archive-help" className="field-help">
              {loadedExample
                ? `Using the ${loadedExample.label} example. Choose a file to use your own instead.`
                : apiConfigured
                  ? "Uploaded straight to storage, never through this site's API."
                  : "Only needed against a deployed API. The fixture flow doesn't need a real archive."}
            </div>
            {archiveError && (
              <div id="terraform-archive-error" className="field-error" role="alert">
                Choose a Terraform archive, or pick an example above.
              </div>
            )}
          </>
        ) : (
          <>
            <label htmlFor="terraform-paste">
              Terraform
              <span>Paste one or more .tf files&apos; contents; it&apos;s reviewed as main.tf</span>
            </label>
            <textarea
              id="terraform-paste"
              name="terraformPaste"
              className="code-input"
              rows={12}
              spellCheck={false}
              value={pasted}
              aria-invalid={pasteError}
              aria-describedby={pasteError ? "terraform-paste-error" : "terraform-paste-help"}
              onChange={(event) => setPasted(event.target.value)}
              placeholder={'resource "aws_s3_bucket" "logs" {\n  bucket = "my-logs"\n}'}
            />
            <div id="terraform-paste-help" className="field-help">
              Packed into an archive in your browser and uploaded the same way as a file.
            </div>
            {pasteError && (
              <div id="terraform-paste-error" className="field-error" role="alert">
                {pastedBytes > MAX_PASTE_BYTES
                  ? "That's too much to paste. Upload it as an archive instead."
                  : "Paste the Terraform you want reviewed."}
              </div>
            )}
          </>
        )}

        <label htmlFor="terraform-ref">
          Name for the report
          <span>A repository link, commit, or any name you&apos;ll recognize (label only)</span>
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
          Shown on your report only. ArchiBrief reviews the Terraform above, not this link.
        </div>
        {repoError && (
          <div id="terraform-ref-error" className="field-error" role="alert">
            Enter a name or reference of at least 5 characters.
          </div>
        )}

        <label htmlFor="workload-brief">
          Workload brief
          <span>Purpose, traffic, availability, data sensitivity, and known constraints</span>
        </label>
        <textarea
          id="workload-brief"
          name="workloadBrief"
          rows={6}
          value={values.workloadBrief}
          aria-invalid={briefError}
          aria-describedby={briefError ? "workload-brief-error" : "workload-brief-help"}
          onChange={(event) => setValues({ ...values, workloadBrief: event.target.value })}
          placeholder="Describe what the system does and the constraints the review should evaluate…"
        />
        <div id="workload-brief-help" className="field-help">
          A few sentences stop the review from guessing at missing business context.
        </div>
        {briefError && (
          <div id="workload-brief-error" className="field-error" role="alert">
            Add at least 40 characters of workload context.
          </div>
        )}

        <div className="form-actions">
          {apiConfigured ? (
            <div className="admin-key-control">
              <label htmlFor="admin-key-input">Admin key</label>
              <input
                id="admin-key-input"
                type="password"
                autoComplete="off"
                placeholder="Owner only, for now"
                value={adminKey}
                onChange={(event) => onAdminKeyChange(event.target.value)}
              />
              {/* Kept for this tab only (lib/admin-key.ts); this clears it now. */}
              {adminKey && (
                <button type="button" className="button quiet" onClick={() => onAdminKeyChange("")}>
                  Forget key
                </button>
              )}
            </div>
          ) : (
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
          )}
          <button className="button primary" type="submit" disabled={submitting}>
            {submitting ? "Submitting…" : apiConfigured ? "Start review" : "Continue with fixture"}
          </button>
        </div>
        {notice && (
          <p className="submit-notice" role="alert">
            {notice}
          </p>
        )}
      </form>
    </section>
  );
}
