"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type {
  ChatCitation,
  ChatParagraph,
  ChatTurn,
  DemoChat,
  ReportFinding,
  SuggestedQuestion,
} from "@/lib/contracts";
import { askQuestion, ChatRequestError, fetchQuestions, getApiBaseUrl } from "@/lib/api";
import {
  chatErrorMessage,
  citationLabel,
  MAX_QUESTION_CHARS,
  newClientRequestId,
  remainingLabel,
} from "@/lib/chat";
import { formatFindingId, type ReportSource } from "@/lib/workflow";

interface ReportQuestionsProps {
  reviewId: string;
  source: ReportSource;
  adminKey: string;
  findings: ReportFinding[];
  selectedFindingId: string;
  questionSeed: string;
  seedFindingId: string;
  // Pregenerated suggested answers for a demo review, served as a static
  // file (scripts/pregenerate_demo_chats.py). Samples never call the API.
  demoChat?: DemoChat | null;
  onQuestionSeedConsumed: () => void;
  onOpenFinding: (findingId: string) => void;
  onTranscriptChange: (turns: ChatTurn[]) => void;
  onDownload: () => void;
}

type Mode = "live" | "sample" | "fixture";

const STATUS_LABELS: Record<ChatTurn["status"], string> = {
  answered: "Cited answer",
  not_determinable: "Not determinable from this review",
  refused: "Outside what this chat answers",
};

const FIXTURE_PROMPTS = [
  "Which issues should I address first?",
  "Explain the IAM finding in plain English.",
  "Which changes could affect monthly cost?",
  "What could not be determined?",
];

function modeFor(source: ReportSource): Mode {
  if (source === "live" && getApiBaseUrl()) return "live";
  return source === "fixture" ? "fixture" : "sample";
}

export function ReportQuestions({
  reviewId,
  source,
  adminKey,
  findings,
  selectedFindingId,
  questionSeed,
  seedFindingId,
  demoChat,
  onQuestionSeedConsumed,
  onOpenFinding,
  onTranscriptChange,
  onDownload,
}: ReportQuestionsProps) {
  const mode = modeFor(source);
  const [input, setInput] = useState(questionSeed);
  const [focusFindingId, setFocusFindingId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [suggested, setSuggested] = useState<SuggestedQuestion[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [limit, setLimit] = useState(5);
  const [limitApplies, setLimitApplies] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  const updateTurns = useCallback(
    (next: ChatTurn[]) => {
      setTurns(next);
      onTranscriptChange(next);
    },
    [onTranscriptChange],
  );

  useEffect(() => {
    if (!questionSeed) return;
    setInput(questionSeed);
    setFocusFindingId(seedFindingId || null);
    onQuestionSeedConsumed();
  }, [onQuestionSeedConsumed, questionSeed, seedFindingId]);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    fetchQuestions(reviewId, adminKey)
      .then((transcript) => {
        if (cancelled) return;
        updateTurns(transcript.questions);
        setSuggested(transcript.suggested);
        setRemaining(transcript.questions_remaining);
        setLimit(transcript.limit);
        setLimitApplies(transcript.limit_applies);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setLoadError(
          error instanceof ChatRequestError
            ? chatErrorMessage(error.code)
            : "The conversation couldn't be loaded.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [adminKey, mode, reviewId, updateTurns]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, pending]);

  async function send(request: { question?: string; suggested_id?: string }, shown: string) {
    if (pending) return;
    setNotice("");
    setPending(shown);
    try {
      const response = await askQuestion(
        reviewId,
        {
          client_request_id: newClientRequestId(),
          ...request,
          ...(request.question && focusFindingId ? { focus_finding_id: focusFindingId } : {}),
        },
        adminKey,
      );
      updateTurns([...turns, response]);
      setRemaining(response.questions_remaining);
      setLimit(response.limit);
      setLimitApplies(response.limit_applies);
      if (response.kind === "suggested") {
        setSuggested((current) =>
          current.map((s) => (s.id === response.suggested_id ? { ...s, answered: true } : s)),
        );
      }
      if (request.question) {
        setInput("");
        setFocusFindingId(null);
      }
    } catch (error) {
      const code = error instanceof ChatRequestError ? error.code : "answer_failed";
      setNotice(chatErrorMessage(code));
      if (code === "review_quota_exhausted") setRemaining(0);
    } finally {
      setPending(null);
    }
  }

  function showStored(entry: DemoChat["suggested"][number], index: number) {
    if (turns.some((t) => t.question_id === `demo-${index}`)) return;
    updateTurns([
      ...turns,
      { ...entry, question_id: `demo-${index}`, kind: "suggested", asked_at: null },
    ]);
  }

  function askFixture(question: string) {
    const answer = fixtureAnswer(question, findings, selectedFindingId);
    updateTurns([
      ...turns,
      {
        question_id: `fixture-${turns.length + 1}`,
        kind: "custom",
        suggested_id: null,
        question,
        status: "answered",
        refusal_reason: null,
        answer: [
          {
            text: answer.text,
            citations: [{ kind: "finding", finding_id: answer.findingId, title: "" }],
          },
        ],
        asked_at: null,
        model_id: null,
        prompt_version: null,
      },
    ]);
    setInput("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question) return;
    if (mode === "fixture") {
      askFixture(question);
      return;
    }
    if (question.length > MAX_QUESTION_CHARS) {
      setNotice(chatErrorMessage("invalid_question"));
      return;
    }
    void send({ question }, question);
  }

  const exhausted = mode === "live" && limitApplies && remaining !== null && remaining <= 0;
  const canType = mode === "fixture" || (mode === "live" && !loadError);

  return (
    <section
      className="report-section questions-section"
      id="ask-review"
      aria-labelledby="questions-heading"
    >
      <div className="section-heading-row">
        <div>
          <span className="section-kicker">After the report</span>
          <h2 id="questions-heading">Ask ArchiBrief about this review</h2>
          <p>
            Every answer cites this review&apos;s findings or AWS guidance, or says it can&apos;t
            tell.
          </p>
        </div>
        <span className="concept-label">
          {mode === "live"
            ? "Cited answers"
            : mode === "sample"
              ? "Sample answers"
              : "Preview feature"}
        </span>
      </div>

      <div className="grounding-note">
        <span aria-hidden="true">✓</span>
        <p>
          <strong>Bound to this report snapshot</strong>
          Answers use the workload brief, the findings and their evidence, the resource settings and
          AWS Well-Architected guidance. They can&apos;t see live AWS and never change the report.
        </p>
      </div>

      {mode === "live" && suggested.length > 0 && (
        <div className="suggested-prompts" aria-label="Suggested questions">
          {suggested.map((s) => (
            <button
              type="button"
              key={s.id}
              disabled={Boolean(pending)}
              onClick={() => void send({ suggested_id: s.id }, s.question)}
            >
              {s.question}
              <span className="chip-note">{s.answered ? "free · instant" : "free"}</span>
            </button>
          ))}
        </div>
      )}
      {mode === "sample" && demoChat && demoChat.suggested.length > 0 && (
        <div className="suggested-prompts" aria-label="Suggested questions">
          {demoChat.suggested.map((entry, index) => (
            <button
              type="button"
              key={entry.suggested_id ?? index}
              onClick={() => showStored(entry, index)}
            >
              {entry.question}
            </button>
          ))}
        </div>
      )}
      {mode === "fixture" && (
        <div className="suggested-prompts" aria-label="Suggested questions">
          {FIXTURE_PROMPTS.map((prompt) => (
            <button type="button" key={prompt} onClick={() => askFixture(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      )}

      <div
        className="chat-log"
        ref={logRef}
        aria-live="polite"
        aria-busy={Boolean(pending)}
        aria-label="Report questions and answers"
      >
        {turns.length === 0 && !pending && (
          <article className="chat-message assistant">
            <span>ArchiBrief</span>
            <div>
              <p>{introText(mode, Boolean(demoChat?.suggested.length), loadError)}</p>
            </div>
          </article>
        )}
        {turns.map((turn) => (
          <ChatExchange
            key={turn.question_id}
            turn={turn}
            onOpenFinding={onOpenFinding}
            preview={mode === "fixture"}
          />
        ))}
        {pending && (
          <>
            <article className="chat-message user">
              <span>You</span>
              <div>
                <p>{pending}</p>
              </div>
            </article>
            <article className="chat-message assistant" aria-label="Answer in progress">
              <span>ArchiBrief</span>
              <div>
                <p className="chat-pending">Checking the report…</p>
              </div>
            </article>
          </>
        )}
      </div>

      {exhausted ? (
        <div className="question-form question-form-done">
          <p>
            You&apos;ve used this review&apos;s {limit} questions. Download the report with this
            conversation.
          </p>
          <button className="button primary" type="button" onClick={onDownload}>
            Download report
          </button>
        </div>
      ) : (
        <form className="question-form" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="question-input">
            Ask about this architecture review
          </label>
          <input
            id="question-input"
            value={input}
            maxLength={MAX_QUESTION_CHARS}
            disabled={!canType || Boolean(pending)}
            onChange={(event) => {
              setInput(event.target.value);
              if (!event.target.value) setFocusFindingId(null);
            }}
            placeholder={
              canType
                ? "Ask about a finding, tradeoff, source, or fix…"
                : "Live questions open with public reviews"
            }
          />
          <button
            className="button primary"
            type="submit"
            disabled={!canType || Boolean(pending) || !input.trim()}
          >
            Ask
          </button>
        </form>
      )}

      <div className="chat-footer">
        {mode === "live" && remaining !== null && (
          <p
            className={`chat-remaining${limitApplies && remaining <= 1 ? " low" : ""}`}
            role="status"
          >
            {remainingLabel(remaining, limit, limitApplies)}
          </p>
        )}
        {focusFindingId && (
          <p className="chat-focus">
            Asking about {formatFindingId(focusFindingId)}.{" "}
            <button type="button" onClick={() => setFocusFindingId(null)}>
              Clear
            </button>
          </p>
        )}
        {notice && (
          <p className="chat-notice" role="alert">
            {notice}
          </p>
        )}
      </div>
      <p className="chat-disclaimer">
        {mode === "fixture"
          ? "Static interaction preview: no model is called and no conversation is stored."
          : "AI-generated from this review snapshot. Cited answers, not certification. Suggested questions are free; questions you type use this review's allowance. Conversations are kept for 7 days."}
      </p>
    </section>
  );
}

function introText(mode: Mode, hasStored: boolean, loadError: string): string {
  if (loadError) return loadError;
  if (mode === "live") {
    return "Ask about a finding, a tradeoff or a fix, or start with a suggested question.";
  }
  if (mode === "sample") {
    return hasStored
      ? "These answers were generated once from this sample review. Pick a question to read its cited answer. Live questions open with public reviews."
      : "Questions work on your own reviews. Live questions on sample reviews open with public reviews.";
  }
  return "I can explain this report or translate its evidence. No model is connected yet; every preview answer stays linked to a typed finding.";
}

function ChatExchange({
  turn,
  onOpenFinding,
  preview,
}: {
  turn: ChatTurn;
  onOpenFinding: (findingId: string) => void;
  preview: boolean;
}) {
  return (
    <>
      <article className="chat-message user">
        <span>You{turn.kind === "suggested" ? " · suggested" : ""}</span>
        <div>
          <p>{turn.question}</p>
        </div>
      </article>
      <article className={`chat-message assistant status-${turn.status}`}>
        <span>
          {preview ? "ArchiBrief · preview" : `ArchiBrief · ${STATUS_LABELS[turn.status]}`}
        </span>
        <div>
          {turn.answer.map((paragraph, index) => (
            <AnswerParagraph
              key={index}
              paragraph={paragraph}
              onOpenFinding={onOpenFinding}
              preview={preview}
            />
          ))}
        </div>
      </article>
    </>
  );
}

function AnswerParagraph({
  paragraph,
  onOpenFinding,
  preview,
}: {
  paragraph: ChatParagraph;
  onOpenFinding: (findingId: string) => void;
  preview: boolean;
}) {
  // Text only, never HTML. The server keeps at most one short code block.
  const parts = paragraph.text.split("```");
  return (
    <div className="chat-paragraph">
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <pre key={index}>
            <code>{part.replace(/^\n/, "")}</code>
          </pre>
        ) : part.trim() ? (
          <p key={index}>{part.trim()}</p>
        ) : null,
      )}
      {paragraph.citations.length > 0 && (
        <ul className="chat-citations" aria-label="Citations">
          {paragraph.citations.map((citation, index) => (
            <li key={index}>
              <Citation citation={citation} onOpenFinding={onOpenFinding} preview={preview} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function safeHref(url: string): string | undefined {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

function Citation({
  citation,
  onOpenFinding,
  preview,
}: {
  citation: ChatCitation;
  onOpenFinding: (findingId: string) => void;
  preview: boolean;
}) {
  if (citation.kind === "finding") {
    return (
      <button
        type="button"
        className="citation-chip"
        onClick={() => onOpenFinding(citation.finding_id)}
      >
        {preview || !citation.title
          ? `View ${formatFindingId(citation.finding_id)} ↑`
          : `${citation.title} ↑`}
      </button>
    );
  }
  if (citation.kind === "source") {
    const href = safeHref(citation.source_url);
    return (
      <details className="citation-source">
        <summary>{citationLabel(citation)}</summary>
        <blockquote>{citation.quote}</blockquote>
        {href && (
          <a href={href} target="_blank" rel="noopener noreferrer">
            Open the AWS source
          </a>
        )}
      </details>
    );
  }
  return (
    <span className="citation-chip static">
      {citation.kind === "resource" ? <code>{citation.address}</code> : citationLabel(citation)}
    </span>
  );
}

// The offline fixture flow's canned answers (no API configured). Kept so
// the fixture demo and its E2E test still work without a backend.
function fixtureAnswer(
  question: string,
  findings: ReportFinding[],
  selectedFindingId: string,
): { text: string; findingId: string } {
  const normalized = question.toLowerCase();
  if (normalized.includes("iam") || normalized.includes("permission")) {
    return {
      findingId: "finding-002",
      text: "The Lambda role can request every S3 action against every S3 resource. A compromised function could therefore reach beyond its audit bucket. The finding recommends narrowing both actions and resource ARNs.",
    };
  }
  if (normalized.includes("cost") || normalized.includes("monthly")) {
    return {
      findingId: "finding-004",
      text: "Multi-AZ can increase standing database cost. This report identifies the tradeoff but lacks live utilization data, so the cost tier is not a dollar forecast.",
    };
  }
  if (normalized.includes("not be determined") || normalized.includes("unknown")) {
    return {
      findingId: "finding-006",
      text: "Data-residency obligations, live AWS state, and remote-module internals were not observable. The report stops those conclusions instead of guessing.",
    };
  }
  if (normalized.includes("first") || normalized.includes("priorit")) {
    return {
      findingId: "finding-001",
      text: "Validate the three high-risk items first: bucket-level public-access protection, the broad Lambda IAM policy, and external CloudTrail coverage. Final implementation order still depends on live controls and ownership.",
    };
  }
  const selected =
    findings.find(({ record }) => record.finding_id === selectedFindingId) ?? findings[0];
  return {
    findingId: selected.record.finding_id,
    text: `${selected.record.evidence} Recommended next step: ${selected.record.recommendation}`,
  };
}
