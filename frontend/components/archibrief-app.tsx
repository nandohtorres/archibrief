"use client";

import { useEffect, useState } from "react";
import { AppHeader } from "./app-header";
import { FailurePanel } from "./state-panel";
import { ClarifyStep } from "./clarify-step";
import { LiveProgressStep } from "./live-progress-step";
import { PreflightStep } from "./preflight-step";
import { ProgressStep } from "./progress-step";
import { ReportWorkspace } from "./report-workspace";
import { SubmissionStep, type SubmissionValues } from "./submission-step";
import {
  fetchReview,
  getApiBaseUrl,
  requestUpload,
  submitClarification,
  submitReview,
  uploadArchiveToS3,
} from "@/lib/api";
import { loadAdminKey, saveAdminKey } from "@/lib/admin-key";
import { fixturePreflightFields, fixtureProgressStages, fixtureReport } from "@/lib/fixtures";
import type { PreflightField, ReviewReport, ReviewStatusPointer } from "@/lib/contracts";
import {
  REVIEW_DEADLINE_MS,
  failureMessageFor,
  makeIdempotencyKey,
  type AppScreen,
} from "@/lib/workflow";

type ThemeChoice = "system" | "light" | "dark";

const emptySubmission: SubmissionValues = {
  terraformRepoRef: "",
  workloadBrief: "",
  archiveFile: null,
};

export function ArchiBriefApp() {
  const [screen, setScreen] = useState<AppScreen>("submission");
  const [theme, setTheme] = useState<ThemeChoice>("system");
  const [adminKey, setAdminKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submission, setSubmission] = useState(emptySubmission);
  const [preflightFields, setPreflightFields] = useState(fixturePreflightFields);
  const [progressIndex, setProgressIndex] = useState(0);
  const [progressMode, setProgressMode] = useState<"fixture" | "live">("fixture");
  const [liveReviewId, setLiveReviewId] = useState<string | null>(null);
  const [liveCurrentStage, setLiveCurrentStage] = useState<string | null>(null);
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0);
  const [clarifyFields, setClarifyFields] = useState<string[]>([]);
  const [clarifySubmitting, setClarifySubmitting] = useState(false);
  const [clarifyError, setClarifyError] = useState<string | null>(null);
  const [report, setReport] = useState<ReviewReport>(fixtureReport);
  const [failureMessage, setFailureMessage] = useState(
    "The fixture failure state shows how ArchiBrief responds when a pipeline stage cannot complete.",
  );
  const apiConfigured = Boolean(getApiBaseUrl());

  useEffect(() => {
    const stored = window.localStorage.getItem("archibrief-theme") as ThemeChoice | null;
    if (stored === "light" || stored === "dark" || stored === "system") setTheme(stored);
    // Tab-scoped, never localStorage (Codex F18) — see lib/admin-key.ts.
    setAdminKey(loadAdminKey(window.sessionStorage, window.localStorage));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("archibrief-theme", theme);
  }, [theme]);

  function handleAdminKeyChange(value: string) {
    setAdminKey(value);
    saveAdminKey(window.sessionStorage, value);
  }

  useEffect(() => {
    if (screen !== "progress" || progressMode !== "fixture") return;
    if (progressIndex >= fixtureProgressStages.length) {
      setScreen("report");
      return;
    }
    const timer = window.setTimeout(() => setProgressIndex((current) => current + 1), 650);
    return () => window.clearTimeout(timer);
  }, [progressIndex, progressMode, screen]);

  // Real polling of GET /reviews/{reviewId}. A failed run is marked
  // status "failed" with a public failureCode by the backend
  // (mark_review_failed), so polling stops on it. The deadline covers the
  // pipeline's own worst case (AgentCore alone may take 300s) so a slow
  // success is never reported as a failure.
  useEffect(() => {
    if (screen !== "progress" || progressMode !== "live" || !liveReviewId) return;
    let cancelled = false;
    let attempts = 0;
    const intervalMs = 3000;
    const maxAttempts = Math.ceil(REVIEW_DEADLINE_MS / intervalMs);
    const poll = async () => {
      attempts += 1;
      try {
        const result = await fetchReview(liveReviewId, adminKey);
        if (cancelled) return;
        setLiveCurrentStage((result as ReviewStatusPointer).currentStage ?? null);
        if (result.status === "complete") {
          setReport(result as ReviewReport);
          setScreen("report");
          return;
        }
        // Found 2026-10-12, live-tested: before this, "needs_clarification"
        // was treated identically to "still pending" — the poll loop just
        // kept counting toward the same 120s timeout, so a review that was
        // genuinely paused waiting on the user (Step Functions can wait up
        // to 7 days at StoreClarificationToken) looked indistinguishable
        // from a dead one. Exit the poll loop immediately instead and show
        // the real question(s).
        if (result.status === "needs_clarification") {
          const pointer = result as ReviewStatusPointer;
          setClarifyFields(pointer.needsClarification ?? []);
          setClarifyError(null);
          setScreen("clarify");
          return;
        }
        if (result.status === "failed") {
          setFailureMessage(failureMessageFor((result as ReviewStatusPointer).failureCode));
          setScreen("failure");
          return;
        }
        if (attempts >= maxAttempts) {
          console.error("review polling deadline exceeded", {
            reviewId: liveReviewId,
            lastStatus: result.status,
          });
          setFailureMessage(
            "This review is taking much longer than expected. Please try again in a few minutes.",
          );
          setScreen("failure");
          return;
        }
        window.setTimeout(poll, intervalMs);
      } catch (error) {
        if (cancelled) return;
        setFailureMessage(
          error instanceof Error
            ? `Could not retrieve review status: ${error.message}`
            : "Could not retrieve review status.",
        );
        setScreen("failure");
      }
    };
    setLiveElapsedSeconds(0);
    const elapsedTimer = window.setInterval(
      () => setLiveElapsedSeconds((seconds) => seconds + 1),
      1000,
    );
    const firstPoll = window.setTimeout(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(elapsedTimer);
      window.clearTimeout(firstPoll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, progressMode, liveReviewId]);

  async function handleSubmission(values: SubmissionValues) {
    setSubmission(values);
    if (!apiConfigured) {
      setPreflightFields(fixturePreflightFields);
      setScreen("preflight");
      return;
    }

    if (!values.archiveFile) {
      // SubmissionStep's own validation already blocks this in the UI —
      // guarded again here since handleSubmission is the actual contract
      // boundary (archive_s3_key is hard-required by the state machine).
      setFailureMessage("A Terraform archive is required to submit to the deployed API.");
      setScreen("failure");
      return;
    }

    setSubmitting(true);
    try {
      // review_id doubles as the idempotency token server-side (no
      // separate idempotencyKey field exists — see lib/contracts.ts,
      // Work-Project-Issues-Log.md 2026-10-01). retrieval_query has no
      // separate input in this step, so it defaults to the workload
      // brief text itself, the same fallback deeper_review's handler
      // uses when no narrower technical query is available.
      const reviewId = makeIdempotencyKey();

      // ADR-0045 (2026-10-12): the archive goes straight to S3 via a
      // presigned POST, tied to reviewId before the review itself exists
      // anywhere server-side — only the resulting key is sent to
      // POST /reviews, never the file bytes.
      const upload = await requestUpload({ review_id: reviewId }, adminKey);
      await uploadArchiveToS3(upload, values.archiveFile);

      const response = await submitReview(
        {
          review_id: reviewId,
          archive_s3_key: upload.archiveKey,
          terraform_repo_ref: values.terraformRepoRef,
          workload_brief: values.workloadBrief,
          retrieval_query: values.workloadBrief,
          baseline_answers: {},
        },
        adminKey,
      );
      setLiveReviewId(response.reviewId);
      setLiveCurrentStage(null);
      setProgressMode("live");
      setScreen("progress");
    } catch (error) {
      setFailureMessage(
        error instanceof Error
          ? error.message
          : "The deployed submission endpoint could not start this review.",
      );
      setScreen("failure");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleClarifySubmit(answers: Record<string, string>, additionalNotes: string) {
    if (!liveReviewId) return;
    setClarifySubmitting(true);
    setClarifyError(null);
    try {
      await submitClarification(
        liveReviewId,
        { answers, additional_notes: additionalNotes || undefined },
        adminKey,
      );
      // Resuming via SendTaskSuccess happens server-side (clarify_review
      // Lambda); re-entering "progress" restarts the same live-polling
      // effect from a fresh attempt count, same as the original submission.
      setScreen("progress");
    } catch (error) {
      setClarifyError(
        error instanceof Error ? error.message : "Could not submit the clarification answer.",
      );
    } finally {
      setClarifySubmitting(false);
    }
  }

  function handlePreflightComplete(fields: PreflightField[]) {
    const traffic = fields.find((field) => field.id === "expected_traffic_scale")?.value;
    setReport({
      ...fixtureReport,
      terraform_repo_ref: submission.terraformRepoRef || fixtureReport.terraform_repo_ref,
      baseline_answers: fixtureReport.baseline_answers.map((answer) =>
        answer.field === "expected_traffic_scale" && traffic
          ? { ...answer, value: traffic }
          : answer,
      ),
    });
    setProgressIndex(0);
    setProgressMode("fixture");
    setScreen("progress");
  }

  function preview(nextScreen: AppScreen) {
    if (nextScreen === "progress") {
      setProgressMode("fixture");
      setProgressIndex(2);
    }
    if (nextScreen === "failure") {
      setFailureMessage(
        "The review stopped before finalization because the AgentCore reasoning runtime is not deployed. The incomplete result was not published as an evidence ledger.",
      );
    }
    setScreen(nextScreen);
  }

  return (
    <div className="app-shell">
      <AppHeader
        apiConfigured={apiConfigured}
        screen={screen}
        theme={theme}
        onThemeChange={setTheme}
        onPreview={preview}
        adminKey={adminKey}
        onAdminKeyChange={handleAdminKeyChange}
      />
      <main id="main-content">
        {screen === "submission" && (
          <SubmissionStep
            apiConfigured={apiConfigured}
            initialValues={submission}
            submitting={submitting}
            onSubmit={handleSubmission}
          />
        )}
        {screen === "preflight" && (
          <PreflightStep
            initialFields={preflightFields}
            onBack={() => setScreen("submission")}
            onContinue={handlePreflightComplete}
          />
        )}
        {screen === "progress" && progressMode === "live" && liveReviewId && (
          <LiveProgressStep
            reviewId={liveReviewId}
            currentStage={liveCurrentStage}
            elapsedSeconds={liveElapsedSeconds}
            onCancel={() => setScreen("submission")}
          />
        )}
        {screen === "progress" && progressMode === "fixture" && (
          <ProgressStep
            activeIndex={Math.min(progressIndex, fixtureProgressStages.length - 1)}
            stages={fixtureProgressStages}
            onSkip={() => setScreen("report")}
          />
        )}
        {screen === "clarify" && liveReviewId && (
          <ClarifyStep
            reviewId={liveReviewId}
            fields={clarifyFields}
            submitting={clarifySubmitting}
            error={clarifyError}
            onSubmit={handleClarifySubmit}
            onCancel={() => setScreen("submission")}
          />
        )}
        {screen === "report" && (
          <ReportWorkspace
            report={report}
            adminKey={adminKey}
            onNewReview={() => setScreen("submission")}
          />
        )}
        {screen === "failure" && (
          <FailurePanel
            message={failureMessage}
            onRetry={() => setScreen("submission")}
            onUseFixture={() => setScreen("report")}
          />
        )}
      </main>
      <footer className="site-footer">
        <span>ArchiBrief · auditable second opinion</span>
        <span>
          {apiConfigured
            ? "Static analysis only · never accesses your AWS account"
            : "Fixture build · no live AWS access"}
        </span>
      </footer>
    </div>
  );
}
