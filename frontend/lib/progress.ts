// Maps the backend's real internal pipeline stage names (written by
// infra/modules/step-functions-lambda's RecordStage* ASL states onto the
// review's DynamoDB item as "currentStage") to a small set of GENERIC,
// user-facing macro-stage labels plus a friendlier micro-step
// description. Deliberately NOT a 1:1 passthrough of the internal names
// (Ingest/RuleEngine/InvokeAgent/Validate/Audit/Finalize) — the product
// doesn't disclose its internal pipeline structure to the browser, only
// how far along a bounded sequence of general steps the review is.

export interface ProgressDisplay {
  stageIndex: number;
  totalStages: number;
  macroLabel: string;
  microLabel: string;
  percent: number;
}

interface StageInfo {
  index: number;
  macroLabel: string;
  microLabel: string;
}

const TOTAL_MACRO_STAGES = 4;

// Order matters only for documentation here — percent is computed from
// each stage's own `index`, not array position.
const STAGE_MAP: Record<string, StageInfo> = {
  // Browser-side, before the review exists: the upload and submission.
  uploading: {
    index: 1,
    macroLabel: "Preparing",
    microLabel: "Uploading your Terraform",
  },
  ingest: {
    index: 1,
    macroLabel: "Preparing",
    microLabel: "Reading and screening the submitted configuration",
  },
  rule_engine: {
    index: 2,
    macroLabel: "Analyzing",
    microLabel: "Running deterministic architecture checks",
  },
  reasoning: {
    index: 3,
    macroLabel: "Analyzing",
    microLabel: "Reasoning over the architecture and evidence",
  },
  validate: {
    index: 4,
    macroLabel: "Verifying",
    microLabel: "Checking findings against the evidence schema",
  },
  audit: { index: 4, macroLabel: "Verifying", microLabel: "Recording the audit trail" },
  finalize: { index: 4, macroLabel: "Finalizing", microLabel: "Assembling the final report" },
};

const PENDING_FALLBACK: StageInfo = {
  index: 1,
  macroLabel: "Preparing",
  microLabel: "Starting the review",
};

export function describeProgress(currentStage: string | null | undefined): ProgressDisplay {
  const info = (currentStage && STAGE_MAP[currentStage]) || PENDING_FALLBACK;
  const percent = Math.min(100, Math.round((info.index / TOTAL_MACRO_STAGES) * 100));
  return {
    stageIndex: info.index,
    totalStages: TOTAL_MACRO_STAGES,
    macroLabel: info.macroLabel,
    microLabel: info.microLabel,
    percent,
  };
}
