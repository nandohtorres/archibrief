import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isArchitectureGraph } from "../../frontend/lib/architecture";
import {
  isReviewReport,
  readStakeholderView,
  withStakeholderView,
  type ReviewReport,
  type DemoChat,
} from "../../frontend/lib/contracts";
import { buildReportExport } from "../../frontend/lib/report-review";
import { buildReportHtml } from "../../frontend/lib/chat";
import {
  isDemoEntry,
  reviewerNotesById,
  type DemoEntry,
} from "../../frontend/lib/demos";

const DEMOS = join(__dirname, "../../frontend/public/demos");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(join(DEMOS, path), "utf-8"));
}

const index = readJson("demos.json") as { demos: unknown[] };

describe("demo reviews (lib/demos.ts)", () => {
  it.each(index.demos as DemoEntry[])(
    "keeps $id report, graph, chat and sidecar identities consistent",
    (demo) => {
      const report = readJson(`reports/${demo.id}.json`) as ReviewReport;
      const before = JSON.stringify(report);
      expect(isReviewReport(report)).toBe(true);
      const ids = new Set(report.findings.map((f) => f.record.finding_id));
      expect(ids.size).toBe(report.findings.length);
      expect(
        report.findings.every((f) => f.record.review_id === report.review_id),
      ).toBe(true);
      const graph = readJson(`architecture/${demo.id}.json`);
      expect(isArchitectureGraph(graph)).toBe(true);
      if (!isArchitectureGraph(graph)) throw new Error("Invalid demo graph");
      expect(graph.review_id).toBe(report.review_id);
      const linked = [
        ...graph.account_findings,
        ...graph.nodes.flatMap((n) => n.findings),
      ];
      expect(new Set(linked)).toEqual(ids);
      const sidecar = readStakeholderView(
        readJson(`stakeholder/${demo.id}.json`),
      );
      expect(sidecar?.review_id).toBe(report.review_id);
      expect(new Set(Object.keys(sidecar!.blocks))).toEqual(ids);
      const chat = readJson(`chats/${demo.id}.json`) as DemoChat;
      expect(chat.review_id).toBe(report.review_id);
      for (const turn of chat.suggested)
        for (const paragraph of turn.answer)
          for (const cite of paragraph.citations) {
            if (cite.kind === "finding")
              expect(ids.has(cite.finding_id)).toBe(true);
          }
      const presented = withStakeholderView(report, sidecar!);
      const exported = buildReportExport(presented, [], demo);
      expect(exported.findings.map((f) => f.record.finding_id)).toEqual([
        ...ids,
      ]);
      expect(exported.demo_review?.reviewer_notes).toEqual(
        demo.reviewerNotes ?? [],
      );
      const html = buildReportHtml(presented, [], demo.title, demo);
      expect(html).toContain("Reviewer notes correct or qualify");
      expect(html).not.toMatch(/\$\s*\d[\d,.]*\s*\/(?:mo|month)/i);
      expect(JSON.stringify(report)).toBe(before);
    },
  );
  it("accepts every shipped demo entry", () => {
    expect(index.demos.length).toBe(3);
    expect(index.demos.every(isDemoEntry)).toBe(true);
    // The submission form's example strip shows these short labels.
    for (const demo of index.demos as DemoEntry[]) {
      expect(demo.shortTitle).toBeTruthy();
      expect(demo.tag).toBeTruthy();
    }
  });

  it("rejects entries with unsafe ids or non-https sources", () => {
    const good = index.demos[0] as DemoEntry;
    expect(isDemoEntry({ ...good, id: "../reports/x" })).toBe(false);
    expect(isDemoEntry({ ...good, sourceUrl: "javascript:alert(1)" })).toBe(
      false,
    );
    expect(isDemoEntry({ ...good, reviewerNotes: [{ findingId: "x" }] })).toBe(
      false,
    );
    expect(isDemoEntry({ ...good, shortTitle: 3 })).toBe(false);
    expect(isDemoEntry({ ...good, tag: null })).toBe(false);
  });

  it("ships a saved report and chat for every demo, and every note points at a real finding", () => {
    for (const demo of index.demos as DemoEntry[]) {
      const report = readJson(`reports/${demo.id}.json`) as {
        review_id: string;
        findings: { record: { finding_id: string } }[];
      };
      const chat = readJson(`chats/${demo.id}.json`) as {
        review_id: string;
        suggested: unknown[];
      };
      expect(chat.review_id).toBe(report.review_id);
      expect(chat.suggested.length).toBeGreaterThan(0);
      const ids = new Set(report.findings.map((f) => f.record.finding_id));
      for (const note of demo.reviewerNotes ?? []) {
        expect(ids.has(note.findingId)).toBe(true);
      }
    }
  });

  it("indexes reviewer notes by finding id", () => {
    const breach = (index.demos as DemoEntry[]).find(
      (d) => d.id === "breach-pattern",
    )!;
    const notes = reviewerNotesById(breach);
    expect(notes.size).toBe(5);
    expect(reviewerNotesById(null).size).toBe(0);
  });
});
