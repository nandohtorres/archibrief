// No-monetary-estimates policy (ADR-0062): the shared conformance cases the
// backend also passes (tests/backend/shared/test_money_policy.py), and the
// public projection used by the chat view and both downloads.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  ChatTurn,
  Finding,
  ReviewReport,
} from "../../frontend/lib/contracts";
import { fixtureReport } from "../../frontend/lib/fixtures";
import { buildReportHtml } from "../../frontend/lib/chat";
import { buildReportExport } from "../../frontend/lib/report-review";
import {
  MONEY_POLICY_VERSION,
  QUOTE_OMITTED_NOTE,
  codeWithoutMoney,
  fieldWithoutMoney,
  narrativeWithoutMoney,
} from "../../frontend/lib/money-policy";
import {
  publicParagraph,
  publicRecord,
  publicTurn,
} from "../../frontend/lib/public-projection";

interface Case {
  name: string;
  mode: "field" | "narrative" | "code";
  input: string;
  expected: string;
  removed: number;
}

const CASES = (
  JSON.parse(
    readFileSync(join(__dirname, "../shared/money-policy-cases.json"), "utf-8"),
  ) as { cases: Case[] }
).cases;

const MODES = {
  field: fieldWithoutMoney,
  narrative: narrativeWithoutMoney,
  code: codeWithoutMoney,
};

describe("shared conformance cases", () => {
  it.each(CASES.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(MODES[c.mode](c.input)).toEqual({
      text: c.expected,
      removed: c.removed,
    });
  });
});

const base = fixtureReport.findings[0].record;

function pricedRecord(): Finding {
  return {
    ...base,
    finding_id: "priced",
    type: "inference",
    finding: "Add a standby (about $150/month)",
    evidence:
      'resource "aws_db_instance" "db" multi_az = false # $0.342/hr, name "${var.env}"',
    risk_impact: "An outage costs USD 10,000 an hour.",
    recommendation: "Set multi_az = true.",
    alternatives_considered: [
      { option: "Read replica", reason_rejected: "Costs $90 a month." },
    ],
    citation: base.citation
      ? {
          ...base.citation,
          exact_text_span: "Multi-AZ is billed at $0.342 per hour.",
        }
      : null,
    plain: {
      written_by: "model",
      title: "No standby",
      analogy: "One barn.",
      what_could_happen: "Down for hours.",
      action: "Add a standby for $150 a month.",
      needs_action: true,
      severity: "high",
      harm: "outage",
      fix_components: [{ item: "rds_multi_az", quantity: 1 }],
      effort_hours_low: 4,
      effort_hours_high: 8,
    },
  };
}

describe("public record projection", () => {
  it("removes amounts per field, keeps code syntax and IDs, and lists every change", () => {
    const original = pricedRecord();
    const snapshot = JSON.stringify(original);
    const { record, changed } = publicRecord(original);
    expect(JSON.stringify(original)).toBe(snapshot); // stored record untouched
    expect(record.finding).toBe("Add a standby (about [amount removed])");
    expect(record.risk_impact).toBe("An outage costs [amount removed].");
    expect(record.evidence).toContain('# [amount removed], name "${var.env}"');
    expect(record.alternatives_considered[0].reason_rejected).toBe(
      "Costs [amount removed].",
    );
    expect(record.finding_id).toBe("priced");
    expect(record.confidence).toBe(original.confidence);
    const plain = record.plain as Record<string, unknown>;
    expect(plain.action).toBe("Add a standby for [amount removed].");
    expect(plain).not.toHaveProperty("effort_hours_low");
    expect(plain).not.toHaveProperty("fix_components");
    expect(plain).not.toHaveProperty("harm");
    expect(plain.severity).toBe("high");
    expect(changed).toEqual(
      expect.arrayContaining([
        "finding",
        "risk_impact",
        "evidence",
        "alternatives_considered[0]",
        "plain.action",
        "plain.effort_hours_low (omitted)",
      ]),
    );
    if (base.citation) {
      // An exact quote is omitted, never edited; its anchor stays.
      expect(record.citation?.exact_text_span).toBe("");
      expect(record.citation?.source_url).toBe(base.citation.source_url);
      expect(changed).toContain("citation.exact_text_span (omitted)");
    }
  });

  it("leaves a record with no amounts exactly as it was", () => {
    const { record, changed } = publicRecord(base);
    expect(record).toEqual(base);
    expect(changed).toEqual([]);
  });
});

const pricedTurn: ChatTurn = {
  question_id: "q1",
  kind: "suggested",
  suggested_id: "s1",
  question: "What will it cost?",
  status: "answered",
  refusal_reason: null,
  answer: [
    {
      text: 'A standby helps. It costs about $150 a month.\n```hcl\n# ~$32.85/month\nname = "${var.x}"\necho $1\n```',
      citations: [
        {
          kind: "source",
          quote: "Billed at $0.342 per hour.",
          source_url: "https://docs.aws.amazon.com/x",
          heading_path: "Pricing",
        },
        { kind: "finding", finding_id: "f1", title: "t" },
      ],
    },
  ],
  asked_at: null,
  model_id: "m",
  prompt_version: "p",
};

describe("public chat projection", () => {
  it("cleans an older saved answer the same way the server does", () => {
    const { turn, removed, omitted } = publicTurn(pricedTurn);
    const [paragraph] = turn.answer;
    expect(paragraph.text).toBe(
      'A standby helps.\n```hcl\n# ~[amount removed]\nname = "${var.x}"\necho $1\n```',
    );
    expect(paragraph.amounts_removed).toBe(2);
    expect([removed, omitted]).toEqual([2, 1]);
    const [source, finding] = paragraph.citations;
    expect(source).toMatchObject({
      quote: "",
      quote_omitted: "monetary-amount",
    });
    expect(finding).toEqual(pricedTurn.answer[0].citations[1]);
    expect(pricedTurn.answer[0].text).toContain("$150"); // input untouched
  });

  it("keeps the server's count on an answer it already cleaned", () => {
    const serverCleaned = {
      text: "A standby helps.",
      citations: [],
      amounts_removed: 1,
    };
    const { paragraph, removed } = publicParagraph(serverCleaned);
    expect(paragraph.text).toBe("A standby helps.");
    expect(paragraph.amounts_removed).toBe(1);
    expect(removed).toBe(0);
  });
});

describe("downloads", () => {
  const priced = {
    ...fixtureReport,
    findings: [{ ...fixtureReport.findings[0], record: pricedRecord() }],
  } as ReviewReport;

  it("JSON export is a labelled public copy with no amounts", () => {
    const exported = buildReportExport(priced, [pricedTurn], null);
    const text = JSON.stringify(exported);
    expect(text).not.toMatch(/\$\s?\d+[.,/]|\$\d+ (a|per)|USD \d|\d dollars/);
    expect(text).toContain("${var.x}");
    expect(text).toContain("${var.env}");
    expect(exported.public_text_policy.version).toBe(MONEY_POLICY_VERSION);
    expect(exported.public_text_policy.findings_changed.priced).toContain(
      "finding",
    );
    expect(exported.public_text_policy.chat_amounts_removed).toBe(2);
    expect(exported.public_text_policy.chat_quotes_omitted).toBe(1);
    expect(exported.findings[0].record.finding_id).toBe("priced");
  });

  it("HTML export shows no amounts and says where a quote was left out", () => {
    const html = buildReportHtml(priced, [pricedTurn], "Report");
    expect(html).not.toMatch(/\$\s?\d+[.,/]|\$\d+ (a|per)|USD \d|\d dollars/);
    expect(html).toContain("${var.x}");
    expect(html).toContain("echo $1");
    expect(html).toContain(QUOTE_OMITTED_NOTE.replace(/'/g, "&#39;"));
  });
});
