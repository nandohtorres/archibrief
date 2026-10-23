import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildReportHtml, escapeHtml } from "../../frontend/lib/chat";
import {
  buildReportExport,
  notesForTurn,
  reportSnapshotLabel,
  withEvidenceLabel,
} from "../../frontend/lib/report-review";
import { demoIdFromUrl } from "../../frontend/lib/report-location";
import type { DemoEntry } from "../../frontend/lib/demos";
import type {
  ChatTurn,
  DemoChat,
  ReviewReport,
} from "../../frontend/lib/contracts";

const base = join(__dirname, "../../frontend/public/demos");
const read = (name: string) =>
  JSON.parse(readFileSync(join(base, name), "utf8"));
const demos = read("demos.json").demos as DemoEntry[];

describe("review corrections survive delivery", () => {
  for (const demo of demos) {
    it(`exports every ${demo.id} correction and preserves its generated records`, () => {
      const report = read(`reports/${demo.id}.json`) as ReviewReport;
      const before = JSON.stringify(report);
      const chat = read(`chats/${demo.id}.json`) as DemoChat;
      const turns = chat.suggested.map((entry, i) => ({
        ...entry,
        question_id: `demo-${i}`,
        kind: "suggested",
        asked_at: null,
      })) as ChatTurn[];
      const html = buildReportHtml(report, turns, demo.title, demo);
      const exported = buildReportExport(report, turns, demo);
      for (const note of demo.reviewerNotes ?? []) {
        expect(html).toContain(escapeHtml(note.note));
        expect(exported.demo_review?.reviewer_notes).toContainEqual(note);
      }
      expect(html).toContain(escapeHtml(demo.sourceUrl));
      expect(html).toContain("heuristic, not correctness probability");
      expect(exported.demo_review?.reviewed_at).toBeNull();
      expect(JSON.stringify(report)).toBe(before);
      expect(exported.findings).toEqual(report.findings);
      const cited = notesForTurn(turns[0], demo.reviewerNotes ?? []);
      expect(
        cited.every((note) =>
          turns[0].answer.some((p) =>
            p.citations.some(
              (c) => c.kind === "finding" && c.finding_id === note.findingId,
            ),
          ),
        ),
      ).toBe(true);
    });
  }

  it("escapes annotations and refuses executable source links", () => {
    const demo = {
      ...demos[0],
      sourceUrl: "javascript:alert(1)",
      reviewerNotes: [
        { findingId: "x", verdict: "<img>", note: "<script>alert(1)</script>" },
      ],
    };
    const html = buildReportHtml(
      read("reports/breach-pattern.json"),
      [],
      "Demo",
      demo,
    );
    expect(html).not.toMatch(/<script|<img|href="javascript:/);
    expect(html).toContain("&lt;script&gt;");
  });

  it("uses stored snapshot versions and neutral labels without mutating legacy data", () => {
    const report = read("reports/breach-pattern.json") as ReviewReport;
    const snapshot = reportSnapshotLabel(report.findings);
    for (const { record } of report.findings) {
      if (record.prompt_version)
        expect(snapshot).toContain(record.prompt_version);
      if (record.deterministic_rule_version)
        expect(snapshot).toContain(record.deterministic_rule_version);
    }
    expect(withEvidenceLabel(report.findings[0]).presentation.short_label).toBe(
      "Rule result",
    );
    const fact = report.findings.find((f) => f.record.type === "fact")!;
    expect(withEvidenceLabel(fact).presentation.short_label).toBe(
      "Reported fact",
    );
    expect(fact.presentation.short_label).toBe("Confirmed");
  });
});

it("accepts public demo IDs but never treats a path or capability as a demo", () => {
  expect(demoIdFromUrl("https://archibrief.dev/?demo=fec-database")).toBe(
    "fec-database",
  );
  expect(demoIdFromUrl("https://archibrief.dev/?demo=../secret")).toBeNull();
  expect(demoIdFromUrl("https://archibrief.dev/#submit")).toBeNull();
});
