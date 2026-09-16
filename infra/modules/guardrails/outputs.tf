output "guardrail_id" {
  value = aws_bedrock_guardrail.prompt_attack.guardrail_id
}

output "guardrail_version" {
  value = aws_bedrock_guardrail_version.prompt_attack.version
}
