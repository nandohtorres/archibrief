import { readFileSync } from "node:fs";
import { join } from "node:path";
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
  it("accepts every shipped demo entry", () => {
    expect(index.demos.length).toBe(3);
    expect(index.demos.every(isDemoEntry)).toBe(true);
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
    expect(notes.size).toBe(3);
    expect(reviewerNotesById(null).size).toBe(0);
  });
});
