import type { AnalysisQuality, ReviewReport } from "./contracts";

export function scopeMessage(scope: NonNullable<ReviewReport["analysis_scope"]>): string {
  return (
    "These checks cover supported settings in the submitted configuration. They do not verify deployment, effective access or successful recovery." +
    (scope.truncated
      ? " Some details were omitted due to analysis limits; missing details do not establish absence."
      : "") +
    (scope.incomplete_resources ? " Some expressions could not be checked." : "")
  );
}

export function qualityMessage(quality?: AnalysisQuality): string {
  const descriptions: Record<AnalysisQuality["outcome"], string> = {
    complete:
      "Output checks completed without rejected findings. This does not establish correctness or complete architecture coverage.",
    partial:
      "Analysis is partial: some proposed findings failed output checks. Review the retained findings with these limits in mind.",
    "rules-only":
      "Only deterministic findings were retained. No model findings survived into this report; broader analysis is not established.",
    "all-rejected":
      "All proposed findings were rejected by output checks. An empty report is not a clean review.",
    "no-findings":
      "The analysis produced no findings. This is not a safety guarantee or proof of complete coverage.",
    unknown:
      "Analysis-quality counts were not recorded for this report. Its completeness cannot be established.",
  };
  const message = descriptions[quality?.outcome ?? "unknown"] ?? descriptions.unknown;
  const model = quality?.model_verification;
  const schema = quality?.schema_validation;
  return (
    message +
    (model
      ? ` Model output checks: ${model.accepted} of ${model.attempted} retained, ${model.rejected} rejected.`
      : "") +
    (schema
      ? ` Final schema checks: ${schema.accepted} of ${schema.attempted} retained, ${schema.rejected} rejected.`
      : "")
  );
}
