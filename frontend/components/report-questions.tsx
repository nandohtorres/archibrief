"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { ReportFinding } from "@/lib/contracts";
import { formatFindingId } from "@/lib/workflow";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  findingId?: string;
}

interface ReportQuestionsProps {
  findings: ReportFinding[];
  selectedFindingId: string;
  questionSeed: string;
  onQuestionSeedConsumed: () => void;
  onOpenFinding: (findingId: string) => void;
}

const prompts = [
  "Which issues should I address first?",
  "Explain the IAM finding in plain English.",
  "Which changes could affect monthly cost?",
  "What could not be determined?",
];

export function ReportQuestions({
  findings,
  selectedFindingId,
  questionSeed,
  onQuestionSeedConsumed,
  onOpenFinding,
}: ReportQuestionsProps) {
  const [input, setInput] = useState(questionSeed);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "assistant",
      text: "I can explain this fixture report or translate its evidence. No model is connected; every preview answer stays linked to a typed finding.",
    },
  ]);

  useEffect(() => {
    if (!questionSeed) return;
    setInput(questionSeed);
    onQuestionSeedConsumed();
  }, [onQuestionSeedConsumed, questionSeed]);

  function answerFor(question: string): { text: string; findingId: string } {
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

  function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const answer = answerFor(trimmed);
    setMessages((current) => [
      ...current,
      { id: current.length + 1, role: "user", text: trimmed },
      {
        id: current.length + 2,
        role: "assistant",
        text: answer.text,
        findingId: answer.findingId,
      },
    ]);
    setInput("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    ask(input);
  }

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
          <p>Request a cited explanation after reviewing the findings and architecture impact.</p>
        </div>
        <span className="concept-label">Fixture-only concept</span>
      </div>

      <div className="grounding-note">
        <span aria-hidden="true">✓</span>
        <p>
          <strong>Bound to this report snapshot</strong>
          Answers may use this repository reference, workload brief, typed findings, and captured
          evidence. They cannot inspect live AWS or silently modify the original ledger.
        </p>
      </div>

      <div className="suggested-prompts" aria-label="Suggested questions">
        {prompts.map((prompt) => (
          <button type="button" key={prompt} onClick={() => ask(prompt)}>
            {prompt}
          </button>
        ))}
      </div>

      <div className="chat-log" aria-live="polite" aria-label="Report questions and answers">
        {messages.map((message) => (
          <article className={`chat-message ${message.role}`} key={message.id}>
            <span>{message.role === "user" ? "You" : "ArchiBrief · preview"}</span>
            <div>
              <p>{message.text}</p>
              {message.findingId && (
                <button type="button" onClick={() => onOpenFinding(message.findingId!)}>
                  View {formatFindingId(message.findingId)} ↑
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      <form className="question-form" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="question-input">
          Ask about this architecture review
        </label>
        <input
          id="question-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about a finding, tradeoff, source, or recommendation…"
        />
        <button className="button primary" type="submit">
          Ask
        </button>
      </form>
      <p className="chat-disclaimer">
        Static interaction preview—no model is called and no conversation is stored. Conversational
        behavior remains outside the locked v1 agent flow.
      </p>
    </section>
  );
}
