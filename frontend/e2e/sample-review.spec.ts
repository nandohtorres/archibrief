// Item #7: the public "View sample review" path against GET /demo.
// Network is mocked (page.route) like the rest of the live-build suite;
// GET /demo is free in production, but CI must not depend on AWS.
import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

test.describe("sample review from GET /demo (mocked network)", () => {
  test("opens the sample without an admin key and labels it hypothetical", async ({ page }) => {
    let sentKey: string | undefined = "unset";
    await page.route("**/mock-api/demo", async (route) => {
      sentKey = route.request().headers()["x-admin-key"];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...fixtureReport,
          terraform_repo_ref: "github.com/example/streaming-platform@0000000",
        }),
      });
    });

    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "View sample review" }).first().click();

    await expect(page.locator("#report-heading")).toHaveText(
      "streaming-platform architecture review",
    );
    await expect(page.getByText("Sample review · hypothetical workload")).toBeVisible();
    // UI copy never calls the sample a fixture. (The sample's own citation
    // text is data and is replaced when the real samples are generated.)
    await expect(page.getByText(/this fixture|fixture report|fixture evidence/i)).toHaveCount(0);
    expect(sentKey).toBeUndefined();

    // Going deeper on the precomputed sample must not call the API.
    let deeperCalled = false;
    await page.route(/\/mock-api\/reviews\/.*\/deeper$/, async (route) => {
      deeperCalled = true;
      await route.fulfill({ status: 500, body: "" });
    });
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(page.getByText(/part of the precomputed sample/)).toBeVisible();
    expect(deeperCalled).toBe(false);
  });

  test("shows a friendly failure when the sample can't load", async ({ page }) => {
    await page.route("**/mock-api/demo", (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: '{"message":"boom"}' }),
    );

    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "View sample review" }).first().click();

    await expect(page.getByText(/sample review could not be loaded right now/)).toBeVisible();
    await expect(page.getByText("boom")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "View the sample review" })).toBeVisible();
  });
});
