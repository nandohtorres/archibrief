"use client";

import { useEffect, useRef, useState } from "react";
import { AppHeader, BrandEmblem } from "./app-header";
import { DemoCards } from "./demo-cards";
import { FailurePanel } from "./state-panel";
import { ClarifyStep } from "./clarify-step";
import { LandingClosing, LandingIntro } from "./landing-intro";
import { LiveProgressStep } from "./live-progress-step";
import { PreflightStep } from "./preflight-step";
import { ProgressStep } from "./progress-step";
import { ReportWorkspace } from "./report-workspace";
import { SubmissionStep, type SubmissionValues } from "./submission-step";
import {
  ApiRequestError,
  fetchDemoReport,
  fetchReview,
  getApiBaseUrl,
  requestUpload,
  submitClarification,
  submitReview,
  uploadArchiveToS3,
} from "@/lib/api";
import { archiveDigest } from "@/lib/review-access";
import { publicSubmissionEnabled } from "@/lib/public-access";
import { fixturePreflightFields, fixtureProgressStages, fixtureReport } from "@/lib/fixtures";
import type {
  DemoChat,
  PreflightField,
  ReviewReport,
  ReviewStatusPointer,
  SubmitReviewRequest,
} from "@/lib/contracts";
import type { ArchitectureGraph } from "@/lib/architecture";
import { FEATURED_DEMO_ID, fetchDemo, fetchDemoIndex, type DemoEntry } from "@/lib/demos";
import {
  REVIEW_DEADLINE_MS,
  failureMessageFor,
  makeIdempotencyKey,
  type AppScreen,
  type ReportSource,
} from "@/lib/workflow";

type ThemeChoice = "light" | "dark";

const SUBMISSIONS_CLOSED_NOTICE =
  "New reviews are paused right now. The sample review shows exactly what you'd get back.";

const emptySubmission: SubmissionValues = {
  terraformRepoRef: "",
  workloadBrief: "",
  archiveFile: null,
};

export function ArchiBriefApp() {
  const [screen, setScreen] = useState<AppScreen>("submission");
  const [theme, setTheme] = useState<ThemeChoice>("light");
  const [pendingSection, setPendingSection] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
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
  const [reportSource, setReportSource] = useState<ReportSource>("fixture");
  const [sampleLoading, setSampleLoading] = useState(false);
  // Set only while a demo review is open (reportSource "demo").
  const [demo, setDemo] = useState<DemoEntry | null>(null);
  const [demoChat, setDemoChat] = useState<DemoChat | null>(null);
  const [demoArchitecture, setDemoArchitecture] = useState<ArchitectureGraph | null>(null);
  const [openingDemoId, setOpeningDemoId] = useState<string | null>(null);
  const [failureMessage, setFailureMessage] = useState(
    "The fixture failure state shows how ArchiBrief responds when a pipeline stage cannot complete.",
  );
  const pendingSubmission = useRef<{
    fingerprint: string;
    nonce: string;
    request?: SubmitReviewRequest;
  } | null>(null);
  const apiConfigured = Boolean(getApiBaseUrl());

  useEffect(() => {
    const stored = window.localStorage.getItem("archibrief-theme") as ThemeChoice | null;
    if (stored === "light" || stored === "dark") setTheme(stored);
    // The admin key this site used to keep for the tab is retired.
    window.sessionStorage.removeItem("archibrief-admin-key");
  }, []);

  // Each screen starts at the top; otherwise opening the sample from far
  // down the landing page left the report scrolled to its middle.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [screen]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("archibrief-theme", theme);
  }, [theme]);

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
        const result = await fetchReview(liveReviewId);
        if (cancelled) return;
        setLiveCurrentStage((result as ReviewStatusPointer).currentStage ?? null);
        if (result.status === "complete") {
          setReport(result as ReviewReport);
          setReportSource("live");
          clearDemo();
          setScreen("report");
          return;
        }
        // A review paused for the user (Step Functions can wait up to 7
        // days at StoreClarificationToken) is not "still pending": treating
        // it that way would run into the poll timeout and look like a dead
        // review. Exit the poll loop immediately and show the question(s).
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
  }, [screen, progressMode, liveReviewId]);

  async function handleSubmission(values: SubmissionValues) {
    setSubmission(values);
    setSubmitNotice(null);
    // A build without public submissions answers plainly instead of
    // sending a request the API would refuse.
    if (apiConfigured && !publicSubmissionEnabled) {
      setSubmitNotice(SUBMISSIONS_CLOSED_NOTICE);
      return;
    }
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
      const digest = await archiveDigest(values.archiveFile);
      const fingerprint = JSON.stringify([digest, values.terraformRepoRef, values.workloadBrief]);
      if (pendingSubmission.current?.fingerprint !== fingerprint) {
        pendingSubmission.current = { fingerprint, nonce: makeIdempotencyKey() };
      }
      const pending = pendingSubmission.current;
      if (!pending.request) {
        const upload = await requestUpload({
          archive_size: values.archiveFile.size,
          archive_sha256: digest,
          client_request_id: pending.nonce,
          ...(values.turnstileToken ? { turnstile_token: values.turnstileToken } : {}),
        });
        const version = await uploadArchiveToS3(upload, values.archiveFile);
        pending.request = {
          review_id: upload.reviewId ?? pending.nonce,
          ...(version ? { archive_version_id: version } : {}),
          archive_s3_key: upload.archiveKey,
          terraform_repo_ref: values.terraformRepoRef,
          workload_brief: values.workloadBrief,
          retrieval_query: values.workloadBrief,
          baseline_answers: {},
        };
      }
      const response = await submitReview(pending.request);
      setLiveReviewId(response.reviewId);
      setLiveCurrentStage(null);
      setProgressMode("live");
      setScreen("progress");
    } catch (error) {
      if (error instanceof ApiRequestError && (error.status === 403 || error.status === 429)) {
        // Verification and daily limits: the message says what to do next.
        setSubmitNotice(error.message);
        return;
      }
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

  function goHome() {
    setScreen("submission");
    window.scrollTo({ top: 0 });
  }

  // Header links: scroll to a home page section, rendering home first when
  // another screen is showing.
  function goToSection(id: string) {
    if (screen === "submission") {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    setScreen("submission");
    setPendingSection(id);
  }

  useEffect(() => {
    if (pendingSection && screen === "submission") {
      document.getElementById(pendingSection)?.scrollIntoView();
      setPendingSection(null);
    }
  }, [pendingSection, screen]);

  function clearDemo() {
    setDemo(null);
    setDemoChat(null);
    setDemoArchitecture(null);
  }

  // Opens a finished demo review from its saved files (lib/demos.ts).
  async function showDemo(entry: DemoEntry) {
    const loaded = await fetchDemo(entry);
    setReport(loaded.report);
    setReportSource("demo");
    setDemo(loaded.entry);
    setDemoChat(loaded.chat);
    setDemoArchitecture(loaded.architecture);
    setScreen("report");
  }

  async function openDemo(entry: DemoEntry) {
    setOpeningDemoId(entry.id);
    try {
      await showDemo(entry);
    } catch (error) {
      console.error("demo review could not be loaded", error);
      setFailureMessage(
        "That demo review could not be loaded right now. Please try again shortly.",
      );
      setScreen("failure");
    } finally {
      setOpeningDemoId(null);
    }
  }

  // "View sample review" opens the featured demo: a real, hand-checked
  // review rather than the hypothetical sample. Only if the demo files
  // can't load does it fall back to that sample: GET /demo in a build
  // pointed at the API, the bundled fixture otherwise.
  async function openSample() {
    setSampleLoading(true);
    try {
      const demos = await fetchDemoIndex();
      const featured = demos.find(({ id }) => id === FEATURED_DEMO_ID) ?? demos[0];
      if (featured) {
        await showDemo(featured);
        setSampleLoading(false);
        return;
      }
    } catch (error) {
      console.error("featured demo could not be loaded; falling back", error);
    }
    if (!apiConfigured) {
      setReport(fixtureReport);
      setReportSource("fixture");
      clearDemo();
      setScreen("report");
      setSampleLoading(false);
      return;
    }
    try {
      setReport(await fetchDemoReport());
      setReportSource("sample");
      clearDemo();
      setScreen("report");
    } catch (error) {
      console.error("sample review could not be loaded", error);
      setFailureMessage(
        "The sample review could not be loaded right now. Please try again shortly.",
      );
      setScreen("failure");
    } finally {
      setSampleLoading(false);
    }
  }

  async function handleClarifySubmit(answers: Record<string, string>, additionalNotes: string) {
    if (!liveReviewId) return;
    setClarifySubmitting(true);
    setClarifyError(null);
    try {
      await submitClarification(liveReviewId, {
        answers,
        additional_notes: additionalNotes || undefined,
      });
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
    setReportSource("fixture");
    clearDemo();
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
        onHome={goHome}
        onSection={goToSection}
      />
      <main id="main-content">
        {screen === "submission" && (
          <>
            <LandingIntro
              sampleLoading={sampleLoading}
              onOpenSample={openSample}
              demos={<DemoCards variant="landing" openingId={openingDemoId} onOpen={openDemo} />}
            />
            <div id="submit" className="landing-submit">
              <SubmissionStep
                apiConfigured={apiConfigured}
                initialValues={submission}
                submitting={submitting}
                notice={submitNotice}
                onSubmit={handleSubmission}
                demos={<DemoCards openingId={openingDemoId} onOpen={openDemo} />}
              />
            </div>
            <LandingClosing />
          </>
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
            source={reportSource}
            demo={demo}
            demoChat={demoChat}
            architecture={demoArchitecture}
            onNewReview={() => setScreen("submission")}
          />
        )}
        {screen === "failure" && (
          <FailurePanel
            message={failureMessage}
            onRetry={() => setScreen("submission")}
            onOpenSample={openSample}
            sampleLoading={sampleLoading}
          />
        )}
      </main>
      <footer className="site-footer">
        <div className="footer-brand">
          <BrandEmblem />
          <strong>ArchiBrief</strong>
          <span>Your AWS architecture, briefed</span>
        </div>
        <ul className="site-footer-row">
          {apiConfigured ? (
            <>
              <li>Static analysis only</li>
              <li>Never accesses your AWS account</li>
            </>
          ) : (
            <li>Fixture build · no live AWS access</li>
          )}
          <li>
            <a href="/privacy.html">Privacy</a>
          </li>
          <li>
            <a href="https://github.com/nandohtorres/archibrief">Source on GitHub</a>
          </li>
        </ul>
        <p className="site-footer-legal">
          Reviews are informational and provided as is, without warranty. They are not professional
          security, legal or compliance advice. Demo code belongs to its authors and is shown under
          the license listed with each demo.
        </p>
        <p className="site-footer-copy">
          © 2026 Fernando Torres · An independent project, not affiliated with or endorsed by Amazon
          Web Services. AWS and Terraform are trademarks of their respective owners.
        </p>
      </footer>
    </div>
  );
}
