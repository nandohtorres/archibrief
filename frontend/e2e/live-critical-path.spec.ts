// Covers the visitor's "submit review -> view findings -> 'go deeper'"
// critical path.
// Built against out-public (NEXT_PUBLIC_API_BASE_URL="/mock-api" and public
// submissions baked in at build time - see e2e/dev-server.mjs), with every
// network call intercepted via page.route() and answered locally. This
// deliberately never calls real AWS: a live run would trigger a real, paid
// Step Functions execution (Bedrock/AgentCore) on every CI run, which this
// suite must not do.
import { expect, test, type Page } from "@playwright/test";
import { PUBLIC_URL } from "../playwright.config";
import { fillSubmission } from "./support/submission";
import { mockTurnstile } from "./support/turnstile";
import { fixtureReport } from "../lib/fixtures";

const REVIEW_ID = "12345678-1234-4234-8234-123456789abc";

// The upload reservation and the signed PUT, as the API issues them.
async function mockUpload(page: Page): Promise<void> {
  await page.route("**/mock-api/uploads", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        reviewId: REVIEW_ID,
        archiveKey: `uploads/${REVIEW_ID}/archive.tar`,
        uploadUrl: `${PUBLIC_URL}/mock-api/bound-upload`,
        uploadMethod: "PUT",
        uploadHeaders: { "Content-Type": "application/x-tar", "If-None-Match": "*" },
        readToken: "r".repeat(43),
        writeToken: "w".repeat(43),
        expiresAt: Math.floor(Date.now() / 1000) + 3600,
      }),
    });
  });
  await page.route("**/mock-api/bound-upload", async (route) => {
    await route.fulfill({ status: 200, headers: { "x-amz-version-id": "e2e-version" }, body: "" });
  });
}

test.describe("live critical path (mocked network)", () => {
  test("submit -> poll -> report -> go deeper", async ({ page }) => {
    await mockTurnstile(page);
    await mockUpload(page);
    await page.route("**/mock-api/reviews", async (route) => {
      expect(route.request().headers()["x-admin-key"]).toBeUndefined();
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ reviewId: REVIEW_ID, status: "pending" }),
      });
    });
    // Resolves "complete" on the very first poll - the pending/retry
    // loop itself is covered by the unit tests in tests/frontend for
    // archibrief-app.tsx's polling logic.
    await page.route(/\/mock-api\/reviews\/[^/]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        // A new review carries the diagram Finalize built from its code.
        body: JSON.stringify({
          ...fixtureReport,
          review_id: REVIEW_ID,
          architecture: {
            version: 1,
            lanes: ["data"],
            nodes: [
              {
                id: "aws_s3_bucket.audit_logs",
                type: "aws_s3_bucket",
                label: "s3 bucket",
                name: "audit_logs",
                module: "",
                lane: "data",
                details: ["s3 bucket versioning"],
                findings: ["finding-001"],
              },
            ],
            edges: [],
            account_findings: [],
            truncated: false,
          },
        }),
      });
    });
    await page.route(/\/mock-api\/reviews\/[^/]+\/findings\/[^/]+\/deeper$/, async (route) => {
      expect(route.request().headers()["x-review-write-token"]).toBe("w".repeat(43));
      const deeperFinding = {
        ...fixtureReport.findings[0],
        record: {
          ...fixtureReport.findings[0].record,
          finding_id: "finding-e2e-deeper-001",
          review_id: REVIEW_ID,
        },
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ findings: [deeperFinding] }),
      });
    });

    await page.goto(PUBLIC_URL);
    await expect(page.getByRole("heading", { name: "Submit your Terraform" })).toBeVisible();
    await expect(page.getByLabel("Admin key")).toHaveCount(0);

    await fillSubmission(page);
    await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator("#report-heading")).toBeVisible({ timeout: 20_000 });
    await expect(
      page
        .locator("#architecture-impact")
        .getByRole("button", { name: "s3 bucket audit_logs, 1 finding" }),
    ).toBeVisible();

    await expect(page.getByRole("button", { name: "Go deeper" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(page.getByText(/deeper finding.*added below/)).toBeVisible();
  });

  test("pasted Terraform is uploaded as a tar holding main.tf", async ({ page }) => {
    await mockTurnstile(page);
    await mockUpload(page);
    await page.route("**/mock-api/reviews", async (route) => {
      await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
    });

    // WebKit's request interception drops Blob bodies, so the archive is
    // also read in the page as it's sent.
    await page.addInitScript(() => {
      const send = window.fetch;
      window.fetch = function (input: RequestInfo | URL, init?: RequestInit) {
        if (init?.method === "PUT" && init.body instanceof Blob) {
          void init.body.arrayBuffer().then((buffer) => {
            (window as unknown as { __uploadedFile?: string }).__uploadedFile = new TextDecoder(
              "latin1",
            ).decode(buffer);
          });
        }
        return send.call(window, input, init);
      } as typeof window.fetch;
    });

    await page.goto(PUBLIC_URL);
    await page.getByLabel("Paste code").check();
    await page
      .getByLabel("Terraform code")
      .fill(['resource "aws_s3_bucket" "logs" {', '  bucket = "e2e-logs"', "}", ""].join("\n"));
    await page.getByLabel(/^Report name/).fill("e2e-paste-check");
    await page
      .getByLabel(/^Workload brief/)
      .fill("An internal log bucket for a small team. No regulatory requirements known.");
    await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
    await page.getByRole("button", { name: "Start review" }).click();

    const archive = () =>
      page.evaluate(() => (window as unknown as { __uploadedFile?: string }).__uploadedFile ?? "");
    await expect.poll(archive).toContain("main.tf");
    expect(await archive()).toContain("ustar");
    expect(await archive()).toContain('bucket = "e2e-logs"');
  });
});
