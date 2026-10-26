import type { ReportFinding } from "@/lib/contracts";
import { citationGap, confidenceLabel, formatFindingId } from "@/lib/workflow";
import type { ReviewerNote } from "@/lib/demos";
import { AssessmentTag } from "./assessment-tag";

interface FindingDetailProps {
  finding: ReportFinding;
  onAsk: (finding: ReportFinding) => void;
  // Absent when the report has no architecture diagram.
  onShowArchitecture?: (findingId: string) => void;
  onGoDeeper: (findingId: string) => Promise<void>;
  // A demo's hand-check note on this finding (lib/demos.ts), if any.
  reviewerNote?: ReviewerNote | null;
}

function percentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function FindingDetail({
  finding,
  onAsk,
  onShowArchitecture,
  onGoDeeper,
  reviewerNote = null,
}: FindingDetailProps) {
  const { record, presentation } = finding;
  return (
    <article className="finding-detail" id="finding-detail" aria-live="polite">
      <div className="finding-detail-heading">
        <span className="finding-id">{formatFindingId(record.finding_id)}</span>
        <h3>{record.finding}</h3>
        <div className="finding-tags">
          <AssessmentTag finding={finding} />
          <span className="type-tag">{presentation.short_label}</span>
          <span className="category-tag">{record.category}</span>
          <span className="type-tag">{record.type}</span>
          <span className="confidence-tag">
            Evidence confidence · {confidenceLabel(record.confidence)} (
            {percentage(record.confidence)})
          </span>
        </div>
      </div>

      {reviewerNote && (
        <aside className="reviewer-note" aria-label="Reviewer note">
          <strong>Reviewer note · {reviewerNote.verdict}</strong>
          <p>{reviewerNote.note}</p>
        </aside>
      )}

      <section className="detail-section">
        <h4>Observed evidence</h4>
        <p>{record.evidence}</p>
      </section>
      <section className="detail-section">
        <h4>Risk and impact</h4>
        <p>{record.risk_impact}</p>
      </section>
      <section className="detail-section confidence-section">
        <h4>Why this confidence</h4>
        <div className="confidence-grid">
          <ConfidenceBar
            label="Evidence directness"
            value={record.confidence_inputs.evidence_directness}
          />
          <ConfidenceBar
            label="Source agreement"
            value={record.confidence_inputs.source_agreement}
          />
          <ConfidenceBar
            label="Rule determinism"
            value={record.confidence_inputs.rule_determinism}
          />
        </div>
        <p>
          Confidence is a heuristic built from these three inputs. It describes how direct the
          evidence is, not a probability that the finding is correct or that the architecture is
          safe. A rule scores 100% because it is deterministic; that doesn&apos;t make its
          conclusion right.
        </p>
      </section>

      {record.citation ? (
        <section className="detail-section">
          <h4>Source provenance</h4>
          <dl className="citation-card">
            <div>
              <dt>Source</dt>
              <dd>
                <a
                  href={record.citation.canonical_url ?? record.citation.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {record.citation.source_edition}
                </a>
              </dd>
            </div>
            <div>
              <dt>Section</dt>
              <dd>{record.citation.heading_path}</dd>
            </div>
            <div>
              <dt>Retrieved</dt>
              <dd>
                <time dateTime={record.citation.retrieved_at}>
                  {new Date(record.citation.retrieved_at).toLocaleDateString("en-US", {
                    dateStyle: "medium",
                    timeZone: "UTC",
                  })}
                </time>
              </dd>
            </div>
            <div>
              <dt>Document / chunk</dt>
              <dd className="mono">
                {record.citation.document_id} · {record.citation.chunk_id ?? "whole document"}
              </dd>
            </div>
            <div>
              <dt>Content hash</dt>
              <dd className="mono">{record.citation.content_hash}</dd>
            </div>
            <div>
              <dt>Corpus / parser</dt>
              <dd className="mono">
                {record.citation.corpus_version} · {record.citation.parser_version}
              </dd>
            </div>
            <div className="citation-span">
              <dt>Captured passage</dt>
              <dd>
                <blockquote>{record.citation.exact_text_span}</blockquote>
              </dd>
            </div>
          </dl>
        </section>
      ) : (
        <section className="detail-section evidence-gap">
          <h4>{citationGap(record.type).heading}</h4>
          <p>{citationGap(record.type).body}</p>
        </section>
      )}

      <section className="detail-section recommendation-section">
        <h4>Recommendation</h4>
        <p>{record.recommendation}</p>
        {record.framework_mapping.length > 0 && (
          <div className="framework-tags">
            {record.framework_mapping.map((mapping) => (
              <span key={mapping}>{mapping}</span>
            ))}
          </div>
        )}
      </section>

      {record.alternatives_considered.length > 0 && (
        <details className="alternatives-card">
          <summary>Alternatives considered ({record.alternatives_considered.length})</summary>
          <ul>
            {record.alternatives_considered.map((alternative) => (
              <li key={alternative.option}>
                <strong>{alternative.option}</strong>
                <span>{alternative.reason_rejected}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <details className="snapshot-card">
        <summary>Reproducibility snapshot</summary>
        <dl>
          <div>
            <dt>Depth</dt>
            <dd>{record.depth_level}</dd>
          </div>
          <div>
            <dt>Rule version</dt>
            <dd>{record.deterministic_rule_version ?? "Not applicable"}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{record.model_id ?? "No model used"}</dd>
          </div>
          <div>
            <dt>Prompt</dt>
            <dd>{record.prompt_version ?? "No prompt used"}</dd>
          </div>
          <div>
            <dt>Corpus</dt>
            <dd>{record.corpus_version ?? "No corpus used"}</dd>
          </div>
          <div>
            <dt>Parent finding</dt>
            <dd>{record.parent_finding_id ?? "Original finding"}</dd>
          </div>
        </dl>
      </details>

      <div className="finding-actions">
        {record.type !== "not-observable" && !record.parent_finding_id && (
          <button
            className="button secondary"
            type="button"
            onClick={() => void onGoDeeper(record.finding_id)}
          >
            Go deeper
          </button>
        )}
        {onShowArchitecture && (
          <button
            className="button secondary"
            type="button"
            onClick={() => onShowArchitecture(record.finding_id)}
          >
            Show on architecture
          </button>
        )}
        <button
          className="button secondary"
          type="button"
          onClick={() => onAsk({ record, presentation })}
        >
          Ask about this finding
        </button>
      </div>
    </article>
  );
}

function ConfidenceBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="confidence-row">
      <span>{label}</span>
      <div className="confidence-track" aria-hidden="true">
        <i style={{ width: percentage(value) }} />
      </div>
      <strong>{percentage(value)}</strong>
    </div>
  );
}
