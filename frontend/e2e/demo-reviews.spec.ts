// The finished demo reviews: opened from static files in
// public/demos with no admin key and no API call at all.
import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";

test.describe("demo reviews from saved files", () => {
  test("a demo card opens the saved review with its source, reviewer notes and answers", async ({
    page,
  }) => {
    const apiCalls: string[] = [];
    await page.route("**/mock-api/**", async (route) => {
      apiCalls.push(route.request().url());
      await route.fulfill({ status: 500, body: "" });
    });

    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: /The 2019 bank breach pattern/ }).click();

    await expect(page.locator("#report-heading")).toHaveText("The 2019 bank breach pattern");
    await expect(
      page.getByText("Demo review · real public Terraform, checked by hand"),
    ).toBeVisible();
    const provenance = page.getByRole("complementary", { name: "About this demo" });
    await expect(provenance.getByRole("link", { name: /Rhino Security Labs/ })).toHaveAttribute(
      "href",
      /^https:\/\/github\.com\/RhinoSecurityLabs\//,
    );
    await expect(provenance).toContainText("not Capital One's code");
    await expect(provenance).toContainText("3 findings carry a reviewer note");

    // The stakeholder view shows the note on the finding the model got wrong.
    await page.getByRole("tab", { name: /Guided Report/ }).click();
    await expect(page.getByText("Reviewer note · wrong")).toHaveCount(1);

    // Saved suggested answers read without a model call.
    await page.getByRole("button", { name: "Which issues should I fix first, and why?" }).click();
    await expect(page.getByText(/SSRF-to-S3 attack chain/).first()).toBeVisible();

    // Going deeper on a saved demo starts nothing.
    await page.getByRole("tab", { name: /Evidence Dashboard|Technical/ }).click();
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(page.getByText(/part of the saved demo review/)).toBeVisible();

    expect(apiCalls).toEqual([]);
  });

  test("the landing page's main button opens the featured real demo", async ({ page }) => {
    const apiCalls: string[] = [];
    await page.route("**/mock-api/**", async (route) => {
      apiCalls.push(route.request().url());
      await route.fulfill({ status: 500, body: "" });
    });
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "See a real review" }).first().click();
    await expect(page.locator("#report-heading")).toHaveText("The 2019 bank breach pattern");
    await page.getByRole("tab", { name: /Guided Report/ }).click();
    await expect(page.getByRole("heading", { name: "What this review means" })).toBeVisible();
    expect(apiCalls).toEqual([]);
  });

  test("the architecture diagram is drawn from the demo's code and links to its findings", async ({
    page,
  }) => {
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: /The 2019 bank breach pattern/ }).click();
    const diagram = page.locator("#architecture-impact");
    await expect(diagram.getByRole("heading", { name: "Architecture", exact: true })).toBeVisible();
    // Real resources from the CloudGoat code, not a stock picture.
    const bucket = diagram.getByRole("button", {
      name: /^s3 bucket cg-cardholder-data-bucket, 3 findings$/,
    });
    await expect(bucket).toBeVisible();
    await expect(diagram.getByRole("button", { name: /^internet Internet/ })).toBeVisible();

    await bucket.click();
    await expect(bucket).toHaveAttribute("aria-pressed", "true");
    const panel = diagram.locator(".architecture-panel");
    await expect(panel).toContainText("Configured by: s3 object");
    await panel.getByRole("button", { name: /does not have versioning enabled/ }).click();
    await expect(page.locator("#finding-detail h3")).toContainText(
      "does not have versioning enabled",
    );

    // A finding about something missing is listed apart, not pinned anywhere.
    await expect(diagram.locator(".architecture-account")).toContainText(
      "No aws_cloudtrail resource",
    );

    // From a finding back to the diagram.
    await page.getByRole("button", { name: "Show on architecture" }).click();
    await expect(bucket).toHaveAttribute("aria-pressed", "true");
  });
});
