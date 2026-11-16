import type { ReviewReport } from "@/lib/contracts";
import { publicUnverified, UNVERIFIED_NOTE } from "@/lib/unverified";

export function UnableToVerify({ report }: { report: ReviewReport }) {
  const items = publicUnverified(report.unverified_findings);
  const failed = report.analysis_quality?.reason_codes.includes("model_unavailable");
  const missing =
    !items.length &&
    (report.analysis_quality?.model_verification?.rejected ?? 0) +
      (report.analysis_quality?.schema_validation?.rejected ?? 0) >
      0;
  if (!items.length && !failed && !missing) return null;
  return (
    <details className="unable-to-verify">
      <summary>
        Unable to verify <span className="unverified-badge">{items.length} unverified</span>
        {failed && " - AI analysis did not finish"}
      </summary>
      <p>{UNVERIFIED_NOTE}</p>
      {failed && (
        <p>
          The AI analysis failed or timed out. The findings above include only the checks that
          finished.
        </p>
      )}
      {missing && <p>This report records rejected claims but did not save their text.</p>}
      <ul>
        {items.map((item, index) => (
          <li key={`${item.finding_id}-${index}`}>
            <span className="unverified-badge">Unverified claim</span>
            <h3>{item.finding}</h3>
            {item.resource && (
              <p>
                Resource: <code>{item.resource}</code>
              </p>
            )}
            <p>
              <strong>Why it could not be confirmed:</strong> {item.reason}
            </p>
            {item.evidence && (
              <p>
                <strong>Submitted evidence (unverified):</strong> {item.evidence}
              </p>
            )}
            <p>Recommendation withheld because this item did not pass the checks.</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
