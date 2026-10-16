// The report chat (ADR-0050) on the live build, with the API mocked:
// suggested questions, a typed question with citations, the question
// limit, a server error, and the report download with the conversation.
// Never calls real AWS (each real question is a paid model call).
import { expect, test, type Page } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

const SUGGESTED = [
  { id: "s1", question: "Which issues should I fix first, and why?", answered: false },
  { id: "s3", question: 'How do I fix "Public bucket"?', answered: true },
];

function answer(question: string, kind: "custom" | "suggested", remaining: number) {
  return {
    question_id: `q-${Math.random().toString(16).slice(2)}`,
    kind,
    suggested_id: kind === "suggested" ? "s1" : null,
    question,
    status: "answered",
    refusal_reason: null,
    answer: [
      {
        text: "Start with the broad Lambda role: it can reach every bucket.",
        citations: [
          { kind: "finding", finding_id: "finding-002", title: "Lambda role allows s3:* on *" },
          {
            kind: "source",
            chunk_id: "c1",
            quote: "Grant only the permissions required to perform a task.",
            source_url:
              "https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec03.html",
            heading_path: "Security > SEC03",
          },
        ],
      },
    ],
    asked_at: "2026-10-15T12:00:00Z",
    model_id: "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    prompt_version: "chat_prompt@2026-10-15a",
    questions_remaining: remaining,
    limit: 5,
    limit_applies: true,
  };
}

async function openLiveReport(
  page: Page,
  onAsk: (body: Record<string, string>) => { code?: number; body: object },
) {
  let reviewId = "";
  const asked: Array<Record<string, string>> = [];
  await page.route("**/mock-api/uploads", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        archiveKey: "archive/e2e.tar",
        uploadUrl: `${LIVE_URL}/mock-api/s3-upload`,
        uploadFields: {},
      }),
    }),
  );
  await page.route("**/mock-api/s3-upload", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/mock-api/reviews", async (route) => {
    reviewId = (route.request().postDataJSON() as { review_id: string }).review_id;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route(/\/mock-api\/reviews\/[^/]+$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...fixtureReport, review_id: reviewId }),
    }),
  );
  await page.route(/\/mock-api\/reviews\/[^/]+\/questions$/, async (route) => {
    expect(route.request().headers()["x-admin-key"]).toBe("e2e-admin-key");
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          review_id: reviewId,
          questions: [],
          suggested: SUGGESTED,
          questions_remaining: 2,
          limit: 5,
          limit_applies: true,
        }),
      });
      return;
    }
    const body = route.request().postDataJSON() as Record<string, string>;
    asked.push(body);
    const result = onAsk(body);
    await route.fulfill({
      status: result.code ?? 200,
      contentType: "application/json",
      body: JSON.stringify(result.body),
    });
  });

  await page.goto(LIVE_URL);
  await page.getByLabel("Admin key").fill("e2e-admin-key");
  await page.getByRole("button", { name: /Payments platform/ }).click();
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator("#report-heading")).toBeVisible({ timeout: 20_000 });
  return asked;
}

test.describe("report chat (mocked network)", () => {
  test("suggested and typed questions get cited answers, then the limit", async ({ page }) => {
    let remaining = 2;
    const asked = await openLiveReport(page, (body) => {
      if (body.suggested_id) return { body: answer(SUGGESTED[0].question, "suggested", remaining) };
      remaining -= 1;
      return { body: answer(body.question, "custom", remaining) };
    });

    const chat = page.locator("#ask-review");
    await expect(chat.getByText("2 of 5 questions left on this review")).toBeVisible();
    await expect(
      chat.getByRole("button", { name: /Which issues should I fix first/ }),
    ).toBeVisible();

    // A suggested question: free, so the count doesn't move.
    await chat.getByRole("button", { name: /Which issues should I fix first/ }).click();
    await expect(chat.getByText("Start with the broad Lambda role").first()).toBeVisible();
    expect(asked[0]).toMatchObject({ suggested_id: "s1" });
    expect(asked[0].client_request_id).toMatch(/^[0-9a-f-]{36}$/);
    await expect(chat.getByText("2 of 5 questions left on this review")).toBeVisible();

    // Citations: a finding chip that opens the finding, and a source quote.
    await expect(
      chat.getByRole("button", { name: /Lambda role allows s3:\* on \*/ }).first(),
    ).toBeVisible();
    await chat.getByText("Security > SEC03").first().click();
    await expect(chat.getByText("Grant only the permissions required").first()).toBeVisible();
    await expect(chat.getByRole("link", { name: "Open the AWS source" }).first()).toHaveAttribute(
      "href",
      /^https:\/\/docs\.aws\.amazon\.com\//,
    );

    // A typed question uses one of the review's questions.
    await page.getByLabel("Ask about this architecture review").fill("Why is the role risky?");
    await chat.getByRole("button", { name: "Ask" }).click();
    await expect(chat.getByText("1 of 5 questions left on this review")).toBeVisible();
    expect(asked[1]).toMatchObject({ question: "Why is the role risky?" });
    expect(Object.keys(asked[1]).sort()).toEqual(["client_request_id", "question"]);

    // The last one: the input is replaced by the download.
    await page.getByLabel("Ask about this architecture review").fill("And the bucket?");
    await chat.getByRole("button", { name: "Ask" }).click();
    await expect(chat.getByText(/You've used this review's 5 questions/).first()).toBeVisible();
    await expect(page.getByLabel("Ask about this architecture review")).toHaveCount(0);

    const download = page.waitForEvent("download");
    await chat.getByRole("button", { name: "Download report" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/-report\.html$/);
    const html = await (
      await file.createReadStream()
    )
      .toArray()
      .then((chunks) => Buffer.concat(chunks).toString("utf8"));
    expect(html).toContain("Why is the role risky?");
    expect(html).toContain("Start with the broad Lambda role");
    expect(html).not.toMatch(/<script/i);
  });

  test("server limits show plain messages and keep the question", async ({ page }) => {
    await openLiveReport(page, () => ({
      code: 429,
      body: { error: "daily_cap_reached", message: "server text is never shown" },
    }));
    await page.getByLabel("Ask about this architecture review").fill("What should I fix first?");
    await page.locator("#ask-review").getByRole("button", { name: "Ask" }).click();
    await expect(page.locator("#ask-review").getByRole("alert")).toHaveText(
      /Today's free questions are used up/,
    );
    await expect(page.getByText("server text is never shown")).toHaveCount(0);
    await expect(page.getByLabel("Ask about this architecture review")).toHaveValue(
      "What should I fix first?",
    );
  });

  test("asking about a finding sends that finding as the focus", async ({ page }) => {
    const asked = await openLiveReport(page, (body) => ({
      body: answer(body.question, "custom", 1),
    }));
    await page.getByRole("button", { name: "Ask about this finding" }).first().click();
    await expect(page.getByLabel("Ask about this architecture review")).toHaveValue(
      /^Explain this finding: /,
    );
    await page.locator("#ask-review").getByRole("button", { name: "Ask" }).click();
    await expect.poll(() => asked.length).toBe(1);
    expect(asked[0].focus_finding_id).toBeTruthy();
  });
});
