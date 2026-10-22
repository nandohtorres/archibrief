import { isArchitectureGraph, type ArchitectureGraph } from "./architecture";
import {
  isChatTurn,
  isStakeholderView,
  withStakeholderView,
  type DemoChat,
  type ReviewReport,
} from "./contracts";

// Free demo reviews of real, public Terraform (docs/demos.md). Everything
// is a static file next to the site: visiting never starts a paid review.
//   public/demos/demos.json          the index, briefs and reviewer notes
//   public/demos/reports/<id>.json   the saved review (unedited output)
//   public/demos/chats/<id>.json     pregenerated suggested answers
//   public/demos/architecture/<id>.json  the diagram, built from the code
//                                    (scripts/build_demo_architectures.py)
//   public/demos/stakeholder/<id>.json   plain terms, costs and budget
//                                    (scripts/build_demo_stakeholder.py)

export interface ReviewerNote {
  findingId: string;
  // "wrong", "overstated", "incomplete" or "weak citation".
  verdict: string;
  note: string;
}

export interface DemoEntry {
  id: string;
  title: string;
  subtitle: string;
  // Short label and one-line tag for the submission form's example strip.
  shortTitle?: string;
  tag?: string;
  source: string;
  sourceUrl: string;
  license: string;
  disclaimer: string;
  repoLabel: string;
  brief: string;
  reviewerNotes?: ReviewerNote[];
}

export interface LoadedDemo {
  entry: DemoEntry;
  report: ReviewReport;
  chat: DemoChat | null;
  architecture: ArchitectureGraph | null;
}

const DEMOS_BASE = "/demos";
// What "View sample review" opens.
export const FEATURED_DEMO_ID = "breach-pattern";

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isReviewerNote(value: unknown): value is ReviewerNote {
  if (typeof value !== "object" || value === null) return false;
  const note = value as Record<string, unknown>;
  return isString(note.findingId) && isString(note.verdict) && isString(note.note);
}

export function isDemoEntry(value: unknown): value is DemoEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  const fields = [
    "id",
    "title",
    "subtitle",
    "source",
    "sourceUrl",
    "license",
    "disclaimer",
    "repoLabel",
    "brief",
  ];
  if (!fields.every((field) => isString(entry[field]))) return false;
  if (!/^[a-z0-9-]{1,64}$/.test(entry.id as string)) return false;
  if (!(entry.sourceUrl as string).startsWith("https://")) return false;
  if (![entry.shortTitle, entry.tag].every((field) => field === undefined || isString(field)))
    return false;
  const notes = entry.reviewerNotes;
  return notes === undefined || (Array.isArray(notes) && notes.every(isReviewerNote));
}

function isDemoChat(value: unknown): value is DemoChat {
  if (typeof value !== "object" || value === null) return false;
  const chat = value as Record<string, unknown>;
  return (
    isString(chat.review_id) &&
    Array.isArray(chat.suggested) &&
    chat.suggested.every((entry) =>
      isChatTurn({ ...(entry as object), question_id: "demo", kind: "suggested", asked_at: null }),
    )
  );
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(`${DEMOS_BASE}/${path}`);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

export async function fetchDemoIndex(): Promise<DemoEntry[]> {
  const index = (await getJson("demos.json")) as { demos?: unknown };
  if (!Array.isArray(index.demos)) throw new Error("demos.json: no demos list");
  return index.demos.filter(isDemoEntry);
}

export async function fetchDemo(entry: DemoEntry): Promise<LoadedDemo> {
  const saved = (await getJson(`reports/${entry.id}.json`)) as ReviewReport;
  if (!Array.isArray(saved?.findings) || !isString(saved.review_id)) {
    throw new Error(`reports/${entry.id}.json: not a review`);
  }
  // Optional like the chat: without it the stakeholder view shows the
  // findings' own text.
  let report = saved;
  try {
    const candidate = await getJson(`stakeholder/${entry.id}.json`);
    if (isStakeholderView(candidate) && candidate.review_id === saved.review_id) {
      report = withStakeholderView(saved, candidate);
    }
  } catch {
    report = saved;
  }
  // The chat answers are optional: a demo without them still opens.
  let chat: DemoChat | null = null;
  try {
    const candidate = await getJson(`chats/${entry.id}.json`);
    chat = isDemoChat(candidate) && candidate.review_id === report.review_id ? candidate : null;
  } catch {
    chat = null;
  }
  let architecture: ArchitectureGraph | null = null;
  try {
    const candidate = await getJson(`architecture/${entry.id}.json`);
    architecture =
      isArchitectureGraph(candidate) && candidate.review_id === report.review_id ? candidate : null;
  } catch {
    architecture = null;
  }
  return { entry, report, chat, architecture };
}

export function reviewerNotesById(entry: DemoEntry | null): Map<string, ReviewerNote> {
  return new Map((entry?.reviewerNotes ?? []).map((note) => [note.findingId, note]));
}
