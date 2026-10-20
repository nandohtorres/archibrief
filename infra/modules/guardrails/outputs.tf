output "guardrail_id" {
  value = aws_bedrock_guardrail.prompt_attack.guardrail_id
}

output "guardrail_version" {
  value = aws_bedrock_guardrail_version.prompt_attack.version
}

output "chat_guardrail_id" {
  value = aws_bedrock_guardrail.chat.guardrail_id
}

output "chat_guardrail_version" {
  value = aws_bedrock_guardrail_version.chat.version
}

output "chat_guardrail_arn" {
  value = aws_bedrock_guardrail.chat.guardrail_arn
}

output "chat_grounding_guardrail_id" {
  value = aws_bedrock_guardrail.chat_grounding.guardrail_id
}

output "chat_grounding_guardrail_version" {
  value = aws_bedrock_guardrail_version.chat_grounding.version
}

output "chat_grounding_guardrail_arn" {
  value = aws_bedrock_guardrail.chat_grounding.guardrail_arn
}
