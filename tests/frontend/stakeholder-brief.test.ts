// Stakeholder Brief (ADR-0062): catalog coverage, legacy and new readers,
// ordering, tiers, coverage disclosure and the no-monetary-estimates
// policy on screen and in downloads.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  readStakeholderView,
  withStakeholderView,
  type Finding,
  type ReportFinding,
  type ReviewReport,
} from "../../frontend/lib/contracts";
import { assessmentFor } from "../../frontend/lib/assessment";
import { buildReportHtml } from "../../frontend/lib/chat";
import { buildReportExport } from "../../frontend/lib/report-review";
import { fixtureReport } from "../../frontend/lib/fixtures";
import {
  AMOUNT_PLACEHOLDER,
  BRIEF_ENTRIES,
  PRESENTATION_VERSION,
  TIER_LABELS,
  briefCardFor,
  EVIDENCE_STATE_LABELS,
  briefCoverage,
  evidenceStateFor,
  buildBrief,
  protectionJobs,
  tierFor,
  withoutMoney,
} from "../../frontend/lib/stakeholder-brief";
import { SCENES, SCENE_KEYS } from "../../frontend/lib/brief-scenes";

const ROOT = join(__dirname, "../..");
const DEMOS = join(ROOT, "frontend/public/demos");
const DEMO_IDS = ["breach-pattern", "fec-database", "medicare-platform"];

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf-8"));
}

function demo(id: string): ReviewReport {
  return readJson(join(DEMOS, `reports/${id}.json`)) as ReviewReport;
}

// ---- Fixtures -------------------------------------------------------------

const base = fixtureReport.findings[0].record;

function record(overrides: Partial<Finding>): Finding {
  return {
    ...base,
    citation: null,
    concern: undefined,
    plain: undefined,
    ...overrides,
  };
}

function rule(
  id: string,
  title: string,
  concern?: string | null,
): ReportFinding {
  return {
    record: record({
      finding_id: id,
      type: "deterministic-rule-result",
      finding: title,
      concern,
      risk_impact: "Rule risk text.",
      recommendation: "Rule recommendation.",
    }),
    presentation: { priority: "high", short_label: "Rule result" },
  };
}

const modelPlain = {
  written_by: "model",
  title: "Backups cost about $40/month to add",
  analogy: "Like a spare key under the mat.",
  what_could_happen:
    "Restores could take days; adding them is roughly USD 1,200 a year.",
  action: "Add AWS Backup with a plan costing $3.50 per month.",
  needs_action: true,
  severity: "medium",
  harm: null,
  fix_components: [],
  effort_hours_low: 2,
  effort_hours_high: 6,
};

function assessed(
  finding: ReportFinding,
  severity: "critical" | "high" | "medium" | "low",
): ReportFinding {
  return {
    ...finding,
    assessment: { version: 1, severity, action: "needed", source: "rule" },
  };
}

function model(id: string): ReportFinding {
  return {
    record: record({
      finding_id: id,
      type: "inference",
      finding: "Backups are not configured for ${var.table_name}",
      risk_impact: "Recovery would cost $5,000 or more.",
      recommendation: "Set $BACKUP_PLAN and enable backups.",
      plain: modelPlain,
    }),
    presentation: { priority: "review", short_label: "Review" },
    assessment: {
      version: 1,
      severity: "medium",
      action: "needed",
      source: "model",
    },
  };
}

function report(
  findings: ReportFinding[],
  extra: Partial<ReviewReport> = {},
): ReviewReport {
  return {
    ...fixtureReport,
    created_at: "2026-10-02T12:00:00Z",
    findings,
    ...extra,
  };
}

const scope: NonNullable<ReviewReport["review_scope"]> = {
  version: "review-scope-public@1",
  known_y: 12,
  x: 12,
  count_complete: true,
  model_outcome: "completed",
  categories: { reviewed: 12, zero_copy: 0, unsupported: 0, other: 0 },
  module_gaps: [],
  gaps_complete: true,
  warnings: [],
};

// ---- Catalog --------------------------------------------------------------

// Every concern the backend can emit: rule recipes, configuration checks
// and legacy title inference.
function backendConcerns(): Set<string> {
  const catalog = readFileSync(
    join(ROOT, "backend/shared/stakeholder/catalog.py"),
    "utf-8",
  );
  const recipes = catalog.slice(
    catalog.indexOf("RECIPES: dict"),
    catalog.indexOf("_LEGACY_TITLES"),
  );
  const concerns = new Set(
    [...recipes.matchAll(/^ {4}"([a-z0-9_]+)": Recipe\(/gm)].map((m) => m[1]),
  );
  for (const m of catalog.matchAll(/^\s+\(r".*", "([a-z0-9_]+)"\),?$/gm))
    concerns.add(m[1]);
  const assessment = readFileSync(
    join(ROOT, "backend/shared/assessment.py"),
    "utf-8",
  );
  const block = assessment.slice(
    assessment.indexOf("CONFIGURATION_ASSESSMENTS"),
    assessment.indexOf("}"),
  );
  for (const m of block.matchAll(/"([a-z0-9_]+)":/g)) concerns.add(m[1]);
  return concerns;
}

describe("Stakeholder Brief catalog", () => {
  it("has an entry for every concern the backend can emit, and no others", () => {
    const concerns = backendConcerns();
    expect(concerns.size).toBeGreaterThanOrEqual(34);
    expect(new Set(Object.keys(BRIEF_ENTRIES))).toEqual(concerns);
  });

  it("uses only the agreed tiers, with nat_single needing scoping", () => {
    for (const entry of Object.values(BRIEF_ENTRIES)) {
      expect(["light", "moderate", "major", "needs-scoping"]).toContain(
        entry.tier,
      );
    }
    expect(BRIEF_ENTRIES.nat_single.tier).toBe("needs-scoping");
    expect(BRIEF_ENTRIES.rds_multi_az.tier).toBe("major");
    expect(Object.values(TIER_LABELS)).toEqual([
      "$ Light",
      "$$ Moderate",
      "$$$ Major",
      "Needs scoping",
    ]);
  });

  it("never contains an amount, and pictures only exist where drawn", () => {
    for (const [concern, entry] of Object.entries(BRIEF_ENTRIES)) {
      const text = JSON.stringify(entry);
      expect(withoutMoney(text).removed, concern).toBe(0);
      expect(text).not.toMatch(/\bfree\b/i);
      if (entry.scene) expect(SCENE_KEYS).toContain(entry.scene);
      if (!entry.analogy) expect(entry.scene).toBeNull();
    }
  });

  it("states what the evidence shows for every concern", () => {
    for (const concern of Object.keys(BRIEF_ENTRIES)) {
      expect(
        EVIDENCE_STATE_LABELS[evidenceStateFor(concern)],
        concern,
      ).toBeTruthy();
    }
    expect(evidenceStateFor("rds_multi_az")).toBe("not-shown");
    expect(evidenceStateFor("rds_backup_retention")).toBe("not-shown");
    expect(evidenceStateFor("cloudtrail_present")).toBe("absent");
    expect(evidenceStateFor("sg_open_ingress")).toBe("declared");
    expect(evidenceStateFor("iam_compute_broad_managed")).toBe("derived");
    expect(evidenceStateFor("lambda_secret_env")).toBe("name-match");
    expect(EVIDENCE_STATE_LABELS["not-shown"]).toMatch(
      /left out, set the other way, or depend on a value the files don't include/,
    );
  });

  // Supplementary writing check. The meaning checks are the evidence-case
  // tests under "card derivation"; a phrase list alone proves little.
  it("does not state an unproven absence as fact for not-shown settings", () => {
    const notShown = Object.keys(BRIEF_ENTRIES).filter(
      (c) => evidenceStateFor(c) === "not-shown",
    );
    expect(notShown).toHaveLength(17);
    for (const concern of notShown) {
      const entry = BRIEF_ENTRIES[concern];
      expect(entry.title, concern).not.toMatch(
        /\b(has no|have no|is not|are not|aren't|isn't encrypted|can't|keeps no)\b/i,
      );
      expect(entry.risk, concern).toMatch(/\b(If|Unless|may|could)\b/);
      for (const text of [entry.title, entry.risk, entry.analogy ?? ""]) {
        expect(text, concern).not.toMatch(/\bconfirmed (off|missing)\b/i);
      }
    }
  });

  it("keeps the web firewall to the customer entrance", () => {
    const waf = BRIEF_ENTRIES.cloudfront_waf;
    expect(waf.stillExposed).toMatch(/doesn't come through this entrance/);
    expect(JSON.stringify(BRIEF_ENTRIES)).not.toMatch(/stronger fence/i);
  });
});

// ---- Money policy ---------------------------------------------------------

describe("monetary text policy", () => {
  it("removes amounts but keeps Terraform and shell syntax", () => {
    const { text, removed } = withoutMoney(
      "About $32/month, US$1.5k, USD 1,200 or 40 dollars. Keep ${var.name}, $HOME and $${literal}.",
    );
    expect(removed).toBe(4);
    expect(text).not.toMatch(/\$\d|USD|dollars/);
    expect(text).toContain("${var.name}");
    expect(text).toContain("$HOME");
    expect(text).toContain("$${literal}");
    expect(text.split(AMOUNT_PLACEHOLDER)).toHaveLength(5);
  });

  // Narrative, code and quote handling: tests/frontend/money-policy.test.ts.
});

// ---- Card derivation --------------------------------------------------------

describe("card derivation and legacy reports", () => {
  // The rule fires the same way whether multi_az is false, left out, or set
  // from a variable the files don't include. The card must be true in all
  // three cases, and must not claim the database has no standby.
  it.each([
    [
      "explicitly false",
      'resource "aws_db_instance" "db" has multi_az = false or unset',
    ],
    [
      "left out",
      'resource "aws_db_instance" "db" has multi_az = false or unset',
    ],
    [
      "unresolved variable",
      'resource "aws_db_instance" "db" has multi_az = false or unset',
    ],
  ])(
    "keeps a not-shown setting conditional when it is %s",
    (_case, evidence) => {
      const finding = rule(
        "db",
        "RDS instance 'db' is not configured multi_az",
        "rds_multi_az",
      );
      finding.record.evidence = evidence;
      const card = briefCardFor(finding);
      expect(card.kind).toBe("curated");
      if (card.kind !== "curated") return;
      expect(evidenceStateFor(card.concern)).toBe("not-shown");
      expect(card.entry.title).toMatch(/^The plans don't show/);
      expect(card.entry.risk).toMatch(
        /If it really runs in one Availability Zone/,
      );
      expect(card.entry.work).toMatch(/^Confirm how the database runs today/);
      for (const text of [
        card.entry.title,
        card.entry.risk,
        card.entry.analogy ?? "",
      ]) {
        expect(text).not.toMatch(/has no standby|no standby copy/);
      }
    },
  );

  it("doesn't claim effective access where a permissions boundary may narrow it", () => {
    const entry = BRIEF_ENTRIES.iam_compute_broad_managed;
    expect(entry.title).not.toMatch(/more access than it needs/);
    expect(entry.risk).toMatch(/permissions boundary/);
    expect(BRIEF_ENTRIES.iam_wildcard.risk).toMatch(/permissions boundaries/);
    expect(BRIEF_ENTRIES.iam_wildcard.title).not.toMatch(
      /access to everything/,
    );
  });

  it("only claims a name match for secret-like settings", () => {
    const entry = BRIEF_ENTRIES.lambda_secret_env;
    expect(entry.title).toMatch(/name that suggests/);
    expect(entry.risk).toMatch(/We only checked the name/);
    expect(evidenceStateFor("lambda_secret_env")).toBe("name-match");
  });

  it("keeps an unassessed or not-observable finding as Needs confirmation, never No action", () => {
    const unknown: ReportFinding = {
      ...rule("unk", "Encryption settings could not be read"),
      assessment: undefined,
    };
    unknown.record.type = "not-observable";
    const model = buildBrief(report([unknown]));
    expect(model.noAction).toHaveLength(0);
    expect(model.rows.map((r) => r.finding.record.finding_id)).toEqual(["unk"]);
    expect(assessmentFor(unknown).severity).toBeNull();
    expect(model.unassessedCount).toBe(1);
  });

  it("uses the stored concern first", () => {
    const card = briefCardFor(rule("r1", "Anything", "rds_multi_az"));
    expect(card.kind).toBe("curated");
    expect(card.kind === "curated" && card.concernSource).toBe("recorded");
  });

  it("uses a current backend's brief block for old records without a concern", () => {
    const finding = {
      ...rule("r2", "RDS instance 'db' has no Multi-AZ standby"),
      brief: {
        version: 2 as const,
        concern: "rds_multi_az",
        concern_source: "title" as const,
        subject: "db",
      },
    };
    const card = briefCardFor(finding);
    expect(card.kind === "curated" && card.concern).toBe("rds_multi_az");
    expect(card.kind === "curated" && card.subject).toBe("db");
    // Title inference picks wording only; it never assigns a risk.
    expect(assessmentFor(finding).severity).toBeNull();
  });

  it("reads an older backend's stakeholder card, ignoring its prices and analogy", () => {
    const legacy = {
      ...rule("r3", "Bucket 'logs' is public"),
      stakeholder: {
        source: "rule" as const,
        concern: "s3_public_policy",
        subject: "logs",
        severity: "critical" as const,
        title: "Old title",
        analogy: "Old model-era analogy",
        what_could_happen: "Old",
        action: "Old",
        needs_action: true,
        fix: { monthly_known: 12 },
      } as unknown as ReportFinding["stakeholder"],
    };
    const card = briefCardFor(legacy);
    expect(card.kind === "curated" && card.entry).toBe(
      BRIEF_ENTRIES.s3_public_policy,
    );
    expect(assessmentFor(legacy).severity).toBe("critical");
  });

  it("gives an unknown concern an honest technical fallback with no tier", () => {
    const card = briefCardFor(rule("r4", "Something new", "brand_new_rule"));
    expect(card.kind).toBe("technical");
    expect(tierFor(card)).toBeNull();
  });

  it("gives an AI-written finding a labeled summary, no analogy, needs scoping", () => {
    const card = briefCardFor(model("m1"));
    expect(card.kind).toBe("summary");
    expect(tierFor(card)).toBe("needs-scoping");
    expect(JSON.stringify(card)).not.toContain("spare key");
    expect(card.kind === "summary" && card.moneyRemoved).toBe(true);
    expect(JSON.stringify(card)).not.toMatch(/\$\d|USD/);
  });

  it("never curates a model finding even if it names a concern", () => {
    const finding = model("m2");
    finding.record = { ...finding.record, concern: "rds_multi_az" };
    expect(briefCardFor(finding).kind).toBe("summary");
  });

  it("marks not-observable findings as unchecked", () => {
    const finding = {
      ...rule("n1", "Not checkable"),
      record: record({ finding_id: "n1", type: "not-observable" }),
    };
    const card = briefCardFor(finding);
    expect(card.kind === "technical" && card.notObservable).toBe(true);
    expect(assessmentFor(finding).action).toBe("unknown");
  });
});

// ---- Ordering and coverage ------------------------------------------------

describe("brief model", () => {
  const findings = [
    model("m1"),
    assessed(rule("low", "x", "apigw_throttling"), "low"),
    assessed(rule("crit", "y", "s3_public_policy"), "critical"),
    rule("unk", "z", "brand_new_rule"),
    {
      ...model("none"),
      assessment: {
        version: 1 as const,
        severity: null,
        action: "none" as const,
        source: "model" as const,
      },
    },
  ];

  it("orders by severity, never by tier, keeping finding IDs", () => {
    const brief = buildBrief(report(findings));
    const ids = brief.rows.map((row) => row.finding.record.finding_id);
    const severities = brief.rows.map(
      (row) => assessmentFor(row.finding).severity,
    );
    expect(ids).toEqual(["crit", "m1", "low", "unk"]);
    expect(severities.slice(0, -1)).toEqual(
      [...severities.slice(0, -1)].sort(
        (a, b) =>
          ["critical", "high", "medium", "low"].indexOf(a!) -
          ["critical", "high", "medium", "low"].indexOf(b!),
      ),
    );
    expect(brief.noAction.map((row) => row.finding.record.finding_id)).toEqual([
      "none",
    ]);
    expect(brief.unassessedCount).toBe(1);
    expect(new Set([...ids, "none"])).toEqual(
      new Set(findings.map((f) => f.record.finding_id)),
    );
  });

  it("never implies complete coverage without a recorded scope", () => {
    const missing = briefCoverage(report(findings));
    expect(missing.headline).toMatch(
      /saved before ArchiBrief recorded review scope/,
    );
    expect(missing.headline).toMatch(/Do not read it as complete coverage/);
    expect(missing.details[0]).toMatch(/was not recorded/);
    const recorded = briefCoverage(report(findings, { review_scope: scope }));
    expect(recorded.headline).not.toMatch(
      /saved before ArchiBrief recorded review scope/,
    );
    expect(recorded.details[0]).toMatch(
      /Included 12 of 12 resource declarations/,
    );
    const partial = briefCoverage(
      report(findings, { review_scope: { ...scope, count_complete: false } }),
    );
    expect(partial.headline).toMatch(/partial/);
  });

  it("never reads 'no finding' as 'in place'", () => {
    const jobs = protectionJobs(buildBrief(report([])));
    for (const job of jobs)
      expect(job.status).not.toMatch(/in place|protected/i);
    expect(jobs.find((j) => j.name === "Traffic inspection")?.status).toBe(
      "Not assessed by this review.",
    );
  });
});

// ---- Demo sidecars --------------------------------------------------------

describe("demo sidecars", () => {
  it.each(DEMO_IDS)("%s ships a version 2 sidecar with no amounts", (id) => {
    const raw = readJson(join(DEMOS, `stakeholder/${id}.json`)) as Record<
      string,
      unknown
    >;
    expect(raw.version).toBe(2);
    expect(raw.presentation).toBe(PRESENTATION_VERSION);
    expect(raw).not.toHaveProperty("budget");
    expect(withoutMoney(JSON.stringify(raw)).removed).toBe(0);
    const view = readStakeholderView(raw);
    const saved = demo(id);
    expect(view?.review_id).toBe(saved.review_id);
    const merged = withStakeholderView(saved, view!);
    expect(merged.findings.map((f) => f.record)).toEqual(
      saved.findings.map((f) => f.record),
    );
  });

  it("reads a legacy version 1 sidecar with the same assessments, dropping its budget", () => {
    const legacy = readJson(
      join(
        ROOT,
        "tests/frontend/fixtures/legacy-stakeholder-v1-breach-pattern.json",
      ),
    );
    const current = readJson(join(DEMOS, "stakeholder/breach-pattern.json"));
    const v1 = readStakeholderView(legacy)!;
    const v2 = readStakeholderView(current)!;
    expect(v1.version).toBe(1);
    expect(v2.version).toBe(2);
    const saved = demo("breach-pattern");
    const old = withStakeholderView(saved, v1);
    const now = withStakeholderView(saved, v2);
    expect(old).not.toHaveProperty("budget");
    expect(old.findings.map(assessmentFor)).toEqual(
      now.findings.map(assessmentFor),
    );
    expect(JSON.stringify(old.findings.map((f) => f.stakeholder))).not.toMatch(
      /monthly|inaction/,
    );
  });

  it("rejects malformed and unknown-version sidecars", () => {
    const current = readJson(
      join(DEMOS, "stakeholder/breach-pattern.json"),
    ) as Record<string, unknown>;
    expect(readStakeholderView(null)).toBeNull();
    expect(readStakeholderView({ ...current, version: 3 })).toBeNull();
    const blocks = current.blocks as Record<string, Record<string, unknown>>;
    const [id] = Object.keys(blocks);
    expect(
      readStakeholderView({
        ...current,
        blocks: { [id]: { ...blocks[id], severity: "huge" } },
      }),
    ).toBeNull();
  });
});

// ---- Pictures -------------------------------------------------------------

describe("scenes", () => {
  it("labels both panels and marks unconfirmed parts as unknown", () => {
    for (const key of SCENE_KEYS) {
      const { plans, proposed } = SCENES[key];
      expect(plans.caption.length, key).toBeGreaterThan(0);
      expect(proposed.caption.length, key).toBeGreaterThan(0);
      // An unknown part only appears in the plans panel, and its caption
      // says it was not confirmed.
      expect(
        proposed.items.some((i) => "unknown" in i && i.unknown),
        key,
      ).toBe(false);
    }
    for (const key of ["gate-rule", "listed-address", "logbook"] as const) {
      expect(
        SCENES[key].plans.items.some((i) => "unknown" in i && i.unknown),
      ).toBe(true);
      expect(SCENES[key].plans.caption).toMatch(/not confirmed|confirm first/);
    }
    expect(SCENES["entrance-check"].proposed.caption).toMatch(
      /Other ways in are not covered/,
    );
  });
});

// Rendering of the React view is checked in frontend/e2e/stakeholder-brief.spec.ts:
// this vitest setup runs without a JSX transform (tsconfig jsx: preserve).

describe("downloads", () => {
  const legacyLive = {
    ...report([
      model("m1"),
      rule("crit", "Bucket 'x' policy", "s3_public_policy"),
    ]),
    budget: { monthly_known: 99.5, rows: [] },
  } as ReviewReport;
  const transcript = [
    {
      question_id: "q1",
      kind: "custom" as const,
      suggested_id: null,
      question: "What will it cost?",
      status: "answered" as const,
      refusal_reason: null,
      answer: [
        {
          text: 'Roughly $45/month.\n```\nvar = "${var.x}"\ncost = "$45"\n```',
          citations: [],
        },
      ],
      asked_at: null,
      model_id: null,
      prompt_version: null,
    },
  ];

  it("HTML export: brief per finding, corrections, coverage, no amounts outside code", () => {
    const html = buildReportHtml(legacyLive, transcript, "Report", {
      id: "d",
      title: "d",
      source: "s",
      sourceUrl: "https://example.com",
      license: "MIT",
      disclaimer: "x",
      reviewerNotes: [
        { findingId: "m1", verdict: "wrong", note: "Corrected here." },
      ],
    } as never);
    expect(html).toContain("Stakeholder Brief: A storage bucket");
    expect(html).toContain("Review coverage");
    expect(html).toContain("not recorded for this report");
    expect(html).toContain(
      "Typical overall commitment, not a quote or a verified estimate.",
    );
    expect(html).not.toContain("What it costs to fix");
    const article = html.slice(
      html.indexOf("Backups are not configured"),
      html.indexOf("Stakeholder Brief: A storage bucket"),
    );
    expect(article).toContain("Reviewer note · wrong");
    const withoutCode = html.replace(/<pre>[\s\S]*?<\/pre>/g, "");
    expect(withoutCode).not.toMatch(/\$\d|USD \d/);
    expect(html).toContain("cost = &quot;$45&quot;");
    expect(html).toContain("${var.table_name}");
    expect(html).toContain("@media print");
  });

  it("escapes curated and written text", () => {
    const hostile = model("h1");
    hostile.record = {
      ...hostile.record,
      plain: {
        ...modelPlain,
        what_could_happen: '<img src=x onerror="alert(1)">',
      },
    };
    const html = buildReportHtml(report([hostile]), [], "x");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("JSON export keeps records but drops legacy price blocks", () => {
    const withLegacyCard = {
      ...legacyLive,
      findings: legacyLive.findings.map((f) => ({
        ...f,
        stakeholder: {
          source: "rule",
          concern: "s3_public_policy",
          subject: null,
          severity: "critical",
          title: "t",
          what_could_happen: "w",
          action: "a",
          needs_action: true,
          fix: { monthly_known: 99 },
        } as unknown as ReportFinding["stakeholder"],
      })),
    };
    const exported = buildReportExport(withLegacyCard, [], null);
    expect(exported).not.toHaveProperty("budget");
    expect(
      JSON.stringify(exported.findings.map((f) => f.stakeholder)),
    ).not.toContain("monthly");
    // Records are a labelled public copy: the rule record is unchanged and
    // the model record's price is removed, with the change listed.
    expect(exported.findings[1].record).toEqual(
      withLegacyCard.findings[1].record,
    );
    expect(exported.findings[0].record.risk_impact).toBe(
      "Recovery would cost [amount removed] or more.",
    );
    expect(exported.findings[0].record.recommendation).toContain(
      "$BACKUP_PLAN",
    );
    expect(exported.public_text_policy.findings_changed.m1).toContain(
      "risk_impact",
    );
    expect(exported.stakeholder_brief.presentation).toBe(PRESENTATION_VERSION);
    expect(exported.stakeholder_brief.findings.crit.tier).toBe("light");
  });
});
