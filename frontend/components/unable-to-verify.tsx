import type { ReviewReport, UnverifiedFinding } from "@/lib/contracts";
import { publicUnverified, UNVERIFIED_NOTE, checkTally } from "@/lib/unverified";

function Claims({ items, disproved = false }: { items: UnverifiedFinding[]; disproved?: boolean }) {
  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${item.finding_id}-${index}`}>
          <span className="unverified-badge">
            {disproved ? "Disproved claim" : "Unverified claim"}
          </span>
          <h3>{item.finding}</h3>
          {item.resource && (
            <p>
              Resource: <code>{item.resource}</code>
            </p>
          )}
          <p>
            <strong>Check tally:</strong> {checkTally(item)}
          </p>
          <p>
            <strong>Why it is in this section:</strong> {item.reason}
          </p>
          {item.evidence && (
            <p>
              <strong>Submitted evidence (unverified):</strong> {item.evidence}
            </p>
          )}
          {item.submitted_quote && (
            <p>
              <strong>Submitted quote (not confirmed):</strong> {item.submitted_quote}
            </p>
          )}
          {item.supporting_evidence?.map((ref, i) => (
            <blockquote key={`s-${i}`}>
              <strong>
                Cited supporting {ref.kind}
                {ref.truncated ? " (excerpt)" : ""}:
              </strong>{" "}
              {ref.text}
            </blockquote>
          ))}
          {item.contradicting_evidence?.map((ref, i) => (
            <blockquote key={`c-${i}`}>
              <strong>
                Contradicting {ref.kind}
                {ref.truncated ? " (excerpt)" : ""}:
              </strong>{" "}
              {ref.text}
            </blockquote>
          ))}
          <p>Recommendation withheld because this item did not pass all checks.</p>
        </li>
      ))}
    </ul>
  );
}

export function UnableToVerify({ report }: { report: ReviewReport }) {
  const items = publicUnverified(report.unverified_findings);
  const disproved = publicUnverified(report.disproved_findings);
  const failed = report.analysis_quality?.reason_codes?.includes("model_unavailable");
  const missing =
    !items.length &&
    !disproved.length &&
    (report.analysis_quality?.model_verification?.rejected ?? 0) +
      (report.analysis_quality?.schema_validation?.rejected ?? 0) >
      0;
  return (
    <>
      {items.length || failed || missing ? (
        <details className="unable-to-verify">
          <summary>
            Unable to verify <span className="unverified-badge">{items.length} unverified</span>
            {failed && " - AI analysis did not finish"}
          </summary>
          <p>{UNVERIFIED_NOTE}</p>
          {failed && (
            <p>
              The AI analysis failed or timed out, or could not start. The report includes only the
              checks that finished.
            </p>
          )}
          {missing && <p>This report records rejected claims but did not save their text.</p>}
          <Claims items={items} />
        </details>
      ) : null}
      {disproved.length ? (
        <details className="unable-to-verify disproved-findings">
          <summary>
            Disproved <span className="unverified-badge">{disproved.length} disproved</span>
          </summary>
          <p>
            The supplied facts or guidance contradict these claims. They are retained for inspection
            and excluded from findings totals, the Stakeholder Brief and chat grounding.
          </p>
          <Claims items={disproved} disproved />
        </details>
      ) : null}
    </>
  );
}
