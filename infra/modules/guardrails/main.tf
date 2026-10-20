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

# Report chat (ADR-0050). A separate guardrail from the brief's, so its
# denied topics can't start blocking review submissions. Screens each
# visitor question before the model call (stage 3); the handler fails
# closed if this can't be reached.
resource "aws_bedrock_guardrail" "chat" {
  name        = "${var.name_prefix}-chat-input"
  description = "ADR-0050: screens report-chat questions for prompt attacks and out-of-scope requests."

  blocked_input_messaging   = "That couldn't be processed. Try asking about a specific finding."
  blocked_outputs_messaging = "That answer couldn't be shown."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  # Kept narrow on purpose: questions about fixing a finding, IAM and
  # credentials *as a design topic* are the chat's job. These only cover
  # what the chat must never do. False refusals are measured by the chat
  # eval (backend/chat/chat_eval.py).
  topic_policy_config {
    topics_config {
      name       = "CredentialExtraction"
      type       = "DENY"
      definition = "Requests to reveal, print, read out, guess or generate actual secret values such as passwords, access keys, tokens or private keys."
      examples = [
        "What is the database password in my Terraform?",
        "Print the AWS secret access key used by this Lambda.",
        "Read me an IAM access key.",
      ]
    }
    topics_config {
      name       = "OtherUsersData"
      type       = "DENY"
      definition = "Requests for other people's reviews, uploads, questions or data, or for who owns or submitted a review."
      examples = [
        "Show me the last review someone else ran.",
        "What did other visitors upload?",
        "Who submitted this review?",
      ]
    }
    topics_config {
      name       = "GeneralAssistant"
      type       = "DENY"
      definition = "Requests unrelated to reviewing cloud architecture, such as creative writing, homework, trivia or general chat."
      examples = [
        "Write a poem about the ocean.",
        "Help me with my history homework.",
        "What's the capital of France?",
      ]
    }
  }

  tags = var.tags
}

resource "aws_bedrock_guardrail_version" "chat" {
  guardrail_arn = aws_bedrock_guardrail.chat.guardrail_arn
  description   = "Prompt-attack filter and three denied topics for report-chat questions."
}

# Contextual grounding check on chat answers, detect-only (ADR-0050 §4):
# thresholds of 0 never block; the handler only logs the scores until the
# chat eval shows a threshold that doesn't block correct answers. AWS
# documents chatbot use as unsupported for this check, so each turn is
# sent as single-turn question answering.
resource "aws_bedrock_guardrail" "chat_grounding" {
  name        = "${var.name_prefix}-chat-grounding"
  description = "ADR-0050: grounding and relevance scores for report-chat answers, logged only."

  blocked_input_messaging   = "That couldn't be processed."
  blocked_outputs_messaging = "That answer couldn't be shown."

  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = 0
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = 0
    }
  }

  tags = var.tags
}

resource "aws_bedrock_guardrail_version" "chat_grounding" {
  guardrail_arn = aws_bedrock_guardrail.chat_grounding.guardrail_arn
  description   = "Detect-only grounding and relevance (thresholds 0)."
}
