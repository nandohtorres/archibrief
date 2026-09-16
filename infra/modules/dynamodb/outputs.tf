output "guest_sessions_table_name" {
  value = aws_dynamodb_table.guest_sessions.name
}

output "reviews_table_name" {
  value = aws_dynamodb_table.reviews.name
}

output "findings_table_name" {
  value = aws_dynamodb_table.findings.name
}

output "usage_counters_table_name" {
  value = aws_dynamodb_table.usage_counters.name
}

output "audit_log_table_name" {
  value = aws_dynamodb_table.audit_log.name
}
