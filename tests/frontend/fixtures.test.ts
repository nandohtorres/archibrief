import {
  fixturePreflightFields,
  fixtureReport,
} from "../../frontend/lib/fixtures";

describe("reference fixtures", () => {
  it("represents all three locked preflight pathways", () => {
    expect(fixturePreflightFields.map(({ policy }) => policy)).toEqual([
      "answer",
      "default",
      "stopped",
    ]);
  });

  it("keeps every typed finding attached to the same immutable review", () => {
    const ids = new Set<string>();

    for (const { record } of fixtureReport.findings) {
      expect(record.review_id).toBe(fixtureReport.review_id);
      expect(record.confidence).toBeGreaterThanOrEqual(0);
      expect(record.confidence).toBeLessThanOrEqual(1);
      expect(
        record.confidence_inputs.evidence_directness,
      ).toBeGreaterThanOrEqual(0);
      expect(record.confidence_inputs.source_agreement).toBeGreaterThanOrEqual(
        0,
      );
      expect(record.confidence_inputs.rule_determinism).toBeGreaterThanOrEqual(
        0,
      );
      expect(record.finding).not.toHaveLength(0);
      expect(record.evidence).not.toHaveLength(0);
      expect(record.risk_impact).not.toHaveLength(0);
      expect(record.recommendation).not.toHaveLength(0);
      expect(ids.has(record.finding_id)).toBe(false);
      ids.add(record.finding_id);
    }
  });

  it("uses null citation and provenance for the explicitly not-observable finding", () => {
    const gap = fixtureReport.findings.find(
      ({ record }) => record.type === "not-observable",
    );

    expect(gap).toBeDefined();
    expect(gap?.record.citation).toBeNull();
    expect(gap?.record.model_id).toBeNull();
    expect(gap?.record.prompt_version).toBeNull();
    expect(gap?.record.retrieved_chunk_ids).toEqual([]);
  });

  it("shows complete citation provenance whenever a fixture finding has a citation", () => {
    const cited = fixtureReport.findings.filter(
      ({ record }) => record.citation !== null,
    );

    expect(cited.length).toBeGreaterThan(0);
    for (const { record } of cited) {
      expect(record.citation?.source_url).toMatch(/^https:\/\//);
      expect(record.citation?.retrieved_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
      expect(record.citation?.document_id).not.toHaveLength(0);
      expect(record.citation?.heading_path).not.toHaveLength(0);
      expect(record.citation?.exact_text_span).not.toHaveLength(0);
      expect(record.citation?.parser_version).not.toHaveLength(0);
      expect(record.citation?.corpus_version).not.toHaveLength(0);
    }
  });
});
