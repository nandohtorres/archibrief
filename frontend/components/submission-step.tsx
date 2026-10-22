import { useState, type DragEvent, type FormEvent, type ReactNode } from "react";

import { createTar } from "@/lib/tar";
import { defaultReportName } from "@/lib/workflow";

// The "try it" section of the landing page: where the story turns into
// the product. The submission form, plus:
// - a small strip of finished demo reviews for visitors without Terraform
//   (passed in as `demos`), set apart from the form by a divider;
// - upload a .tar, or paste Terraform (turned into a .tar in the browser,
//   lib/tar.ts, so it takes the same upload + ingest path);
// - the admin key next to the submit button. Submitting stays owner-only
//   until public submissions open (ADR-0046/0047).

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

const ARCHIVE_SUFFIXES = [".tar", ".tar.gz", ".tgz"];

interface SubmissionStepProps {
  apiConfigured: boolean;
  initialValues: SubmissionValues;
  submitting: boolean;
  // Shown under the submit button, e.g. while submissions are owner-only.
  notice?: string | null;
  adminKey: string;
  onAdminKeyChange: (value: string) => void;
  onSubmit: (values: SubmissionValues) => Promise<void>;
  // Finished demo reviews, shown above the form.
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

function isArchiveName(name: string): boolean {
  const lower = name.toLowerCase();
  return ARCHIVE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

function UploadIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3 2 20h20Z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  );
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
  const [attempted, setAttempted] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);

  const pastedBytes = new TextEncoder().encode(pasted).length;
  const briefError = attempted && values.workloadBrief.trim().length < 40;
  const archiveError = attempted && apiConfigured && source === "upload" && !values.archiveFile;
  const pasteError =
    attempted &&
    apiConfigured &&
    source === "paste" &&
    (pasted.trim().length < 20 || pastedBytes > MAX_PASTE_BYTES);

  function chooseArchive(file: File | null) {
    setDropError(null);
    setValues((current) => ({ ...current, archiveFile: file }));
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (!file) return;
    if (!isArchiveName(file.name)) {
      setDropError("That isn't a .tar or .tar.gz archive.");
      return;
    }
    chooseArchive(file);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (values.workloadBrief.trim().length < 40) return;
    const named = (archiveFile: File | null): SubmissionValues => ({
      ...values,
      archiveFile,
      terraformRepoRef: values.terraformRepoRef.trim() || defaultReportName(source, archiveFile),
    });
    if (!apiConfigured) {
      await onSubmit(named(values.archiveFile));
      return;
    }
    if (source === "paste") {
      if (pasted.trim().length < 20 || pastedBytes > MAX_PASTE_BYTES) return;
      await onSubmit(named(pastedArchive(pasted)));
      return;
    }
    if (!values.archiveFile) return;
    await onSubmit(named(values.archiveFile));
  }

  return (
    <section className="flow-card submission-card" aria-labelledby="submission-heading">
      <div className="step-kicker">Try it · Step 1 of 3</div>
      <h2 id="submission-heading">Review your own Terraform</h2>
      <p className="lede">
        ArchiBrief reads the code; it never runs Terraform or touches your AWS account.{" "}
        <span className="owner-only-note">
          New reviews are owner-only for now, because each one uses a paid model.
        </span>
      </p>

      <div className="boundary-callout">
        <WarningIcon />
        <span>
          <strong>Before you submit:</strong> remove secrets and customer data. Modules pulled from
          elsewhere aren&apos;t reviewed; they show up as gaps.
        </span>
      </div>

      {demos}

      <form className="submission-form" onSubmit={handleSubmit} noValidate>
        <div className="form-field">
          <label htmlFor="terraform-ref">
            Report name <span>(optional)</span>
          </label>
          <input
            id="terraform-ref"
            name="terraformRepoRef"
            value={values.terraformRepoRef}
            aria-describedby="terraform-ref-help"
            onChange={(event) => setValues({ ...values, terraformRepoRef: event.target.value })}
            placeholder="my-repo@main"
          />
          <div id="terraform-ref-help" className="field-help">
            Shown as the report&apos;s title. Left blank, we use the file name.
          </div>
        </div>

        <fieldset className="form-field terraform-source">
          <legend>Your Terraform</legend>
          {apiConfigured && (
            <div className="source-switch" role="radiogroup" aria-label="How to add it">
              <label className={source === "upload" ? "selected" : undefined}>
                <input
                  type="radio"
                  name="source"
                  value="upload"
                  checked={source === "upload"}
                  onChange={() => setSource("upload")}
                />
                Upload file
              </label>
              <label className={source === "paste" ? "selected" : undefined}>
                <input
                  type="radio"
                  name="source"
                  value="paste"
                  checked={source === "paste"}
                  onChange={() => setSource("paste")}
                />
                Paste code
              </label>
            </div>
          )}

          {source === "upload" ? (
            <>
              <label
                className={`dropzone${dragging ? " dragging" : ""}${archiveError ? " invalid" : ""}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
              >
                <input
                  id="terraform-archive"
                  name="archiveFile"
                  type="file"
                  accept=".tar,.tar.gz,.tgz"
                  aria-invalid={archiveError}
                  aria-describedby={
                    archiveError ? "terraform-archive-error" : "terraform-archive-help"
                  }
                  onChange={(event) => chooseArchive(event.target.files?.[0] ?? null)}
                />
                <UploadIcon />
                {values.archiveFile ? (
                  <span className="dropzone-title">
                    <strong>{values.archiveFile.name}</strong> · <u>choose another</u>
                  </span>
                ) : (
                  <span className="dropzone-title">
                    Drop a .tar or .tar.gz here, or <u>browse</u>
                  </span>
                )}
                <span id="terraform-archive-help" className="dropzone-hint">
                  {apiConfigured
                    ? "Up to 20 MB · uploaded straight to storage"
                    : "Only needed against a deployed API. The fixture flow doesn't need a real archive."}
                </span>
              </label>
              {(archiveError || dropError) && (
                <div id="terraform-archive-error" className="field-error" role="alert">
                  {dropError ?? "Choose a Terraform archive to review."}
                </div>
              )}
            </>
          ) : (
            <>
              <textarea
                id="terraform-paste"
                name="terraformPaste"
                className="code-input"
                aria-label="Terraform code"
                rows={12}
                spellCheck={false}
                value={pasted}
                aria-invalid={pasteError}
                aria-describedby={pasteError ? "terraform-paste-error" : "terraform-paste-help"}
                onChange={(event) => setPasted(event.target.value)}
                placeholder={'resource "aws_s3_bucket" "logs" {\n  bucket = "my-logs"\n}'}
              />
              <div id="terraform-paste-help" className="field-help">
                Paste one or more .tf files&apos; contents; it&apos;s reviewed as main.tf.
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
        </fieldset>

        <div className="form-field">
          <label htmlFor="workload-brief">Workload brief</label>
          <textarea
            id="workload-brief"
            name="workloadBrief"
            rows={5}
            value={values.workloadBrief}
            aria-invalid={briefError}
            aria-describedby={briefError ? "workload-brief-error" : "workload-brief-help"}
            onChange={(event) => setValues({ ...values, workloadBrief: event.target.value })}
            placeholder="What does it do, who uses it, how much traffic, uptime target, data sensitivity, compliance…"
          />
          <div id="workload-brief-help" className="field-help">
            Used to find the right AWS guidance and decide what matters most. A few sentences is
            enough.
          </div>
          {briefError && (
            <div id="workload-brief-error" className="field-error" role="alert">
              Add at least 40 characters of workload context.
            </div>
          )}
        </div>

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
