import type { AnalysisQuality, ReviewReport } from "./contracts";

export function declarationScopeMessage(scope?: ReviewReport["review_scope"]): string {
  if (!scope || scope.version !== "review-scope-public@1" || scope.known_y === null) {
    return "Resource declaration coverage was not recorded for this report. Start a new review to establish its scope.";
  }
  const total = `${scope.known_y}${scope.count_complete ? "" : " known"} resource declarations`;
  const reviewed =
    scope.model_outcome === "completed" && scope.x !== null
      ? `Included ${scope.x} of ${total} in the completed AI review input.`
      : scope.model_outcome === "not_invoked"
        ? `Counted ${total}. No AI answer-generation call was made.`
        : `Counted ${total}. AI delivery could not be confirmed; the reviewed count is unknown.`;
  const counts = scope.categories
    ? ` Declaration categories: ${scope.categories.zero_copy} zero-copy, ${scope.categories.unsupported} unsupported and ${scope.categories.other} other (including unconfirmed coverage).`
    : "";
  const gaps = scope.module_gaps
    .map((gap) => `${gap.address}: ${gap.labels.join(", ")}`)
    .join("; ");
  const otherReasons = (scope.other_reasons ?? [])
    .map((reason) => `${reason.count} ${reason.label}`)
    .join("; ");
  return (
    reviewed +
    counts +
    (otherReasons ? ` Other declaration reasons: ${otherReasons}.` : "") +
    (scope.count_complete
      ? ""
      : " This is a partial inventory; the whole-workload total is unknown.") +
    (gaps ? ` Module gaps: ${gaps}.` : "") +
    (scope.gaps_complete ? "" : " The module-gap list is incomplete.") +
    (scope.warnings.length ? ` ${scope.warnings.join("; ")}.` : "") +
    " Inclusion does not prove every setting was analyzed or that the deployed system is safe."
  );
}

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
  if (quality?.reason_codes?.includes("model_unavailable")) {
    return "The AI analysis did not finish, so this report holds only the deterministic rule and scanner findings. Issues those checks cannot see are not covered.";
  }
  const message = descriptions[quality?.outcome ?? "unknown"] ?? descriptions.unknown;
  const model = quality?.model_verification;
  const schema = quality?.schema_validation;
  const capped = quality?.reason_codes?.includes("model_findings_capped")
    ? " The AI proposed more findings than a report keeps; the least severe were left out."
    : "";
  return (
    message +
    capped +
    (model
      ? ` Model output checks: ${model.accepted} of ${model.attempted} retained, ${model.rejected} rejected.`
      : "") +
    (schema
      ? ` Final schema checks: ${schema.accepted} of ${schema.attempted} retained, ${schema.rejected} rejected.`
      : "")
  );
}
