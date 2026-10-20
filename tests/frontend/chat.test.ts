import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  isChatTurn,
  isQuestionsTranscript,
  type ChatTurn,
} from "../../frontend/lib/contracts";
import {
  buildReportHtml,
  chatErrorMessage,
  escapeHtml,
  remainingLabel,
} from "../../frontend/lib/chat";

const turn: ChatTurn = {
  question_id: "q1",
  kind: "custom",
  suggested_id: null,
  question: "Why is <b>this</b> risky?",
  status: "answered",
  refusal_reason: null,
  answer: [
    {
      text: 'Narrow the role. <script>alert("x")</script>\n```\nresource "aws_iam_policy" "x" {}\n```',
      citations: [
        {
          kind: "finding",
          finding_id: "f1",
          title: "Role allows <img src=x onerror=1>",
        },
        {
          kind: "source",
          quote: "Grant least privilege",
          source_url: "javascript:alert(1)",
          heading_path: "Security > SEC03",
        },
        {
          kind: "source",
          quote: "Use roles",
          source_url: "https://docs.aws.amazon.com/wellarchitected/x.html",
          heading_path: "Security > SEC02",
        },
      ],
    },
  ],
  asked_at: "2026-10-15T12:00:00Z",
  model_id: "us.anthropic.claude-haiku-4-5-20251001-v1:0",
  prompt_version: "chat_prompt@2026-10-15a",
};

describe("report chat helpers (ADR-0050)", () => {
  it("escapes every HTML-significant character", () => {
    expect(escapeHtml(`<a href="x">'&'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;",
    );
    expect(escapeHtml(null)).toBe("");
  });

  it("builds a download where no model or report text becomes markup", () => {
    const html = buildReportHtml(
      fixtureReport,
      [turn],
      "payments-api <review>",
    );
    expect(html).not.toContain("<script>alert");
    expect(html).not.toContain("<img src=x");
    expect(html).not.toContain("<b>this</b>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("<title>payments-api &lt;review&gt;</title>");
    // Only http(s) links from the server's records become links.
    expect(html).not.toContain('href="javascript:');
    expect(html).toContain(
      'href="https://docs.aws.amazon.com/wellarchitected/x.html"',
    );
    // The kept code block renders as preformatted text.
    expect(html).toContain("<pre>resource &quot;aws_iam_policy&quot;");
    // No scripts at all in the file itself.
    expect(html).not.toMatch(/<script/i);
    expect(html).toContain("Conversation");
    expect(html).toContain("not compliance certification");
  });

  it("says so when no questions were asked", () => {
    expect(buildReportHtml(fixtureReport, [], "r")).toContain(
      "No questions were asked.",
    );
  });

  it("labels the remaining questions plainly", () => {
    expect(remainingLabel(4, 5, true)).toBe(
      "4 of 5 questions left on this review",
    );
    expect(remainingLabel(0, 5, true)).toBe(
      "You've used this review's 5 questions",
    );
    expect(remainingLabel(5, 5, false)).toBe("Owner access: no question limit");
  });

  it("maps every server error code to fixed text", () => {
    expect(chatErrorMessage("daily_cap_reached")).toMatch(/used up/);
    expect(chatErrorMessage("review_quota_exhausted")).toMatch(
      /used this review/,
    );
    expect(chatErrorMessage("<script>")).toBe(
      "Something went wrong asking that question.",
    );
  });

  it("accepts real chat responses and rejects other shapes", () => {
    expect(isChatTurn(turn)).toBe(true);
    expect(isChatTurn({ ...turn, status: "maybe" })).toBe(false);
    expect(isChatTurn({ ...turn, answer: [{ text: 1 }] })).toBe(false);
    expect(isChatTurn({ error: "review_not_found" })).toBe(false);
    expect(
      isQuestionsTranscript({
        review_id: "r1",
        questions: [turn],
        suggested: [],
        questions_remaining: 4,
        limit: 5,
        limit_applies: true,
      }),
    ).toBe(true);
    expect(isQuestionsTranscript({ review_id: "r1", questions: [{}] })).toBe(
      false,
    );
  });
});
