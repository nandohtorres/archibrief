# Terraform module: guardrails
# Deploys the real Bedrock Guardrail that backs GuardrailsClient
# (backend/shared/clients/__init__.py) — the production prompt-attack
# control decided in ADR-0033 (Bedrock Guardrails' prompt-attack
# detection replaces the Custom-Model-Import path ADR-0014 proposed,
# which AWS's own docs show doesn't support the intended model
# architecture). Runs inline at Ingest and again before Reason
# (see backend/agent/nodes/reason.py's module docstring) — this module
# only creates the one shared Guardrail resource both call sites use by
# ID + version, not two separate Guardrails.
#
# Guardrails does not inspect retrieved/tool results (ADR-0038) — that's
# a separate, deterministic-allowlist control, not this resource's job.

resource "aws_bedrock_guardrail" "prompt_attack" {
  name        = "${var.name_prefix}-prompt-attack"
  description = "ADR-0033: prompt-attack detection on ArchiBrief's workload-brief input surface (Ingest + Reason)."

  blocked_input_messaging   = "This request could not be processed for safety reasons."
  blocked_outputs_messaging = "This response could not be generated for safety reasons."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  tags = var.tags
}

resource "aws_bedrock_guardrail_version" "prompt_attack" {
  guardrail_arn = aws_bedrock_guardrail.prompt_attack.guardrail_arn
  description   = "Initial version — prompt-attack detection only, no content filters configured yet."
}
