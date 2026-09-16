"use client";

import { useEffect, useState } from "react";
import { AppHeader } from "./app-header";
import { FailurePanel } from "./state-panel";
import { PreflightStep } from "./preflight-step";
import { ProgressStep } from "./progress-step";
import { ReportWorkspace } from "./report-workspace";
import { SubmissionStep, type SubmissionValues } from "./submission-step";
import { getApiBaseUrl, submitReview } from "@/lib/api";
import { fixturePreflightFields, fixtureProgressStages, fixtureReport } from "@/lib/fixtures";
import type { PreflightField, ReviewReport } from "@/lib/contracts";
import { makeIdempotencyKey, type AppScreen } from "@/lib/workflow";

type ThemeChoice = "system" | "light" | "dark";

const emptySubmission: SubmissionValues = { terraformRepoRef: "", workloadBrief: "" };

export function ArchiBriefApp() {
  const [screen, setScreen] = useState<AppScreen>("submission");
  const [theme, setTheme] = useState<ThemeChoice>("system");
  const [adminKey, setAdminKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submission, setSubmission] = useState(emptySubmission);
  const [preflightFields, setPreflightFields] = useState(fixturePreflightFields);
  const [progressIndex, setProgressIndex] = useState(0);
  const [report, setReport] = useState<ReviewReport>(fixtureReport);
  const [failureMessage, setFailureMessage] = useState(
    "The fixture failure state shows how ArchiBrief responds when a pipeline stage cannot complete.",
  );
  const apiConfigured = Boolean(getApiBaseUrl());

  useEffect(() => {
    const stored = window.localStorage.getItem("archibrief-theme") as ThemeChoice | null;
    if (stored === "light" || stored === "dark" || stored === "system") setTheme(stored);
    // No user accounts (ADR-0044) — the admin key is a single pre-shared
    // credential, not a session token, so it's fine to persist locally.
    setAdminKey(window.localStorage.getItem("archibrief-admin-key") ?? "");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("archibrief-theme", theme);
  }, [theme]);

  function handleAdminKeyChange(value: string) {
    setAdminKey(value);
    window.localStorage.setItem("archibrief-admin-key", value);
  }

  useEffect(() => {
    if (screen !== "progress") return;
    if (progressIndex >= fixtureProgressStages.length) {
      setScreen("report");
      return;
    }
    const timer = window.setTimeout(() => setProgressIndex((current) => current + 1), 650);
    return () => window.clearTimeout(timer);
  }, [progressIndex, screen]);

  async function handleSubmission(values: SubmissionValues) {
    setSubmission(values);
    if (!apiConfigured) {
      setPreflightFields(fixturePreflightFields);
      setScreen("preflight");
      return;
    }

    setSubmitting(true);
    try {
      const response = await submitReview(
        {
          terraformRepoRef: values.terraformRepoRef,
          workloadBrief: values.workloadBrief,
          idempotencyKey: makeIdempotencyKey(),
        },
        adminKey,
      );
      setFailureMessage(
        `Review ${response.reviewId} was accepted with status “${response.status}”, but GET /reviews/{reviewId} is not deployed, so this client cannot follow or retrieve the run yet.`,
      );
      setScreen("failure");
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
    setScreen("progress");
  }

  function preview(nextScreen: AppScreen) {
    if (nextScreen === "progress") setProgressIndex(2);
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
        {screen === "progress" && (
          <ProgressStep
            activeIndex={Math.min(progressIndex, fixtureProgressStages.length - 1)}
            stages={fixtureProgressStages}
            onSkip={() => setScreen("report")}
          />
        )}
        {screen === "report" && (
          <ReportWorkspace report={report} onNewReview={() => setScreen("submission")} />
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
        <span>Fixture build · no live AWS access</span>
      </footer>
    </div>
  );
}
