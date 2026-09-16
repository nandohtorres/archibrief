output "agent_runtime_arn" {
  description = "Wire this into modules/step-functions-lambda's agentcore_runtime_arn input to replace its placeholder ARN."
  value       = aws_bedrockagentcore_agent_runtime.review.agent_runtime_arn
}

output "execution_role_arn" {
  value = aws_iam_role.agentcore_execution.arn
}
