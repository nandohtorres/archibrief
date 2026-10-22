// Covers the "admin-gated submit review -> view findings -> 'go deeper'"
// critical path.
// Built against out-live (NEXT_PUBLIC_API_BASE_URL="/mock-api" baked in
// at build time - see e2e/dev-server.mjs), with every network call
// intercepted via page.route() and answered locally. This deliberately
// never calls real AWS: a live run would trigger a real, paid Step
// Functions execution (Bedrock/AgentCore) on every CI run, which this
// suite must not do.
import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fillSubmission } from "./support/submission";
import { fixtureReport } from "../lib/fixtures";

test.describe("admin-gated live critical path (mocked network)", () => {
  test("submit -> poll -> report -> go deeper", async ({ page }) => {
    // The review_id sent to the mocked API is a fresh idempotency key
    // generated client-side (makeIdempotencyKey) - capture whatever
    // actual ID the app used so the poll loop's GET can be answered
    // with a matching reviewId, rather than assuming a fixed one.
    let capturedReviewId = "";

    await page.route("**/mock-api/uploads", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          archiveKey: "archive/e2e-test.tar",
          uploadUrl: `${LIVE_URL}/mock-api/s3-upload`,
          uploadFields: {},
        }),
      });
    });
    await page.route("**/mock-api/s3-upload", async (route) => {
      await route.fulfill({ status: 204, body: "" });
    });
    await page.route("**/mock-api/reviews", async (route) => {
      const body = route.request().postDataJSON() as { review_id: string };
      capturedReviewId = body.review_id;
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
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
          review_id: capturedReviewId,
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
      const deeperFinding = {
        ...fixtureReport.findings[0],
        record: {
          ...fixtureReport.findings[0].record,
          finding_id: "finding-e2e-deeper-001",
          review_id: capturedReviewId,
        },
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ findings: [deeperFinding] }),
      });
    });

    await page.goto(LIVE_URL);
    await expect(page.getByRole("heading", { name: "Review your own Terraform" })).toBeVisible();
    await page.getByLabel("Admin key").fill("e2e-admin-key");

    await fillSubmission(page);
    await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator("#report-heading")).toBeVisible({ timeout: 20_000 });
    expect(capturedReviewId).not.toBe("");
    await expect(
      page
        .locator("#architecture-impact")
        .getByRole("button", { name: "s3 bucket audit_logs, 1 finding" }),
    ).toBeVisible();

    await expect(page.getByRole("button", { name: "Go deeper" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(page.getByText(/deeper finding.*added below/)).toBeVisible();
  });

  test("admin key is tab-scoped, sent with requests, and can be forgotten", async ({ page }) => {
    // Regression: the key must not persist in localStorage.
    let sentKey: string | undefined;
    await page.route("**/mock-api/uploads", async (route) => {
      sentKey = route.request().headers()["x-admin-key"];
      await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
    });

    await page.goto(LIVE_URL);
    await page.getByLabel("Admin key").fill("e2e-admin-key");

    const stored = await page.evaluate(() => ({
      session: window.sessionStorage.getItem("archibrief-admin-key"),
      local: window.localStorage.getItem("archibrief-admin-key"),
    }));
    expect(stored).toEqual({ session: "e2e-admin-key", local: null });

    await page.reload();
    await expect(page.getByLabel("Admin key")).toHaveValue("e2e-admin-key");

    await fillSubmission(page);
    await page.getByRole("button", { name: "Start review" }).click();
    await expect.poll(() => sentKey).toBe("e2e-admin-key");

    // The key field lives in the form (next to "Start review"), so return
    // to it; the key is still there for this tab, and can be forgotten.
    await page.goto(LIVE_URL);
    await expect(page.getByLabel("Admin key")).toHaveValue("e2e-admin-key");
    await page.getByRole("button", { name: "Forget key" }).click();
    await expect(page.getByLabel("Admin key")).toHaveValue("");
    expect(
      await page.evaluate(() => window.sessionStorage.getItem("archibrief-admin-key")),
    ).toBeNull();
  });
  test("pasted Terraform is uploaded as a tar holding main.tf", async ({ page }) => {
    let uploaded = "";
    await page.route("**/mock-api/uploads", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          archiveKey: "archive/e2e-paste.tar",
          uploadUrl: `${LIVE_URL}/mock-api/s3-upload`,
          uploadFields: {},
        }),
      });
    });
    await page.route("**/mock-api/s3-upload", async (route) => {
      uploaded = route.request().postDataBuffer()?.toString("latin1") ?? "";
      await route.fulfill({ status: 204, body: "" });
    });
    await page.route("**/mock-api/reviews", async (route) => {
      await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
    });

    // WebKit's request interception drops Blob bodies from FormData, so
    // the archive is also read in the page as it's appended.
    await page.addInitScript(() => {
      const append = FormData.prototype.append;
      FormData.prototype.append = function (
        this: FormData,
        name: string,
        value: string | Blob,
        filename?: string,
      ) {
        if (value instanceof Blob) {
          void value.arrayBuffer().then((buffer) => {
            (window as unknown as { __uploadedFile?: string }).__uploadedFile = new TextDecoder(
              "latin1",
            ).decode(buffer);
          });
        }
        return Reflect.apply(
          append,
          this,
          filename === undefined ? [name, value] : [name, value, filename],
        );
      } as typeof FormData.prototype.append;
    });

    await page.goto(LIVE_URL);
    await page.getByLabel("Paste code").check();
    await page
      .getByLabel("Terraform code")
      .fill(['resource "aws_s3_bucket" "logs" {', '  bucket = "e2e-logs"', "}", ""].join("\n"));
    await page.getByLabel(/^Report name/).fill("e2e-paste-check");
    await page
      .getByLabel(/^Workload brief/)
      .fill("An internal log bucket for a small team. No regulatory requirements known.");
    await page.getByLabel("Admin key").fill("e2e-admin-key");
    await page.getByRole("button", { name: "Start review" }).click();

    await expect.poll(() => uploaded).toContain('filename="pasted-terraform.tar"');
    const archive = () =>
      page.evaluate(() => (window as unknown as { __uploadedFile?: string }).__uploadedFile ?? "");
    await expect.poll(archive).toContain("main.tf");
    expect(await archive()).toContain("ustar");
    expect(await archive()).toContain('bucket = "e2e-logs"');
  });
});
