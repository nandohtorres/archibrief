// Covers the "static guest/demo report view" critical path: the no-API fixture
// walkthrough every visitor without an admin key sees (ADR-0044: no
// user accounts). No network mocking here on purpose: this path makes
// zero real fetch calls by design (archibrief-app.tsx's apiConfigured
// guard), so running it unmocked is itself part of what's being
// verified.
import { expect, test } from "@playwright/test";

import { FIXTURE_URL } from "../playwright.config";

test.describe("fixture/demo critical path (no live API)", () => {
  test("submission -> preflight -> progress -> report -> go deeper (fixture-only)", async ({
    page,
  }) => {
    await page.goto(FIXTURE_URL);

    await expect(page.getByRole("heading", { name: "Submit your Terraform" })).toBeVisible();
    await page.getByRole("button", { name: "Load reference fixture" }).click();
    await page.getByRole("button", { name: "Continue with fixture" }).click();

    await expect(
      page.getByRole("heading", { name: "Resolve only what the review genuinely needs" }),
    ).toBeVisible();
    await page.locator("#preflight-expected_traffic_scale").fill("~40 requests/second at peak");
    await page.getByRole("button", { name: "Accept shown default" }).click();
    await page.getByRole("button", { name: "Start fixture review" }).click();

    await expect(page.locator("#live-progress-heading")).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Review progress" })).toBeVisible();
    await expect(
      page.getByText("Sample preview. No upload or AI review is running."),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Building a reproducible evidence ledger" }),
    ).toHaveCount(0);
    await expect(page.getByText("The review keeps running.", { exact: false })).toHaveCount(0);

    // The fixture progress animation auto-advances every 650ms through
    // real stage identifiers before switching to the report
    // screen - no real work happens, this just exercises that the
    // state machine itself reaches "report".
    await expect(page.locator("#report-heading")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("button", { name: "Go deeper" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(
      page.getByText(/Fixture only:.*would create a versioned child finding/),
    ).toBeVisible();
  });
});
