data "aws_kms_alias" "source" {
  name = "alias/aws/s3"
}

resource "aws_iam_role_policy" "storage_key" {
  for_each = merge({ worker = aws_iam_role.review_worker.name },
    { for name, role in aws_iam_role.lambda : name => role.name if contains(["ingest", "scan", "rule_engine", "finalize"], name) })
  role = each.value
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = contains(["scan", "rule_engine"], each.key) ? ["kms:Decrypt"] : ["kms:Decrypt", "kms:GenerateDataKey"]
      Resource = data.aws_kms_alias.source.target_key_arn
      Condition = { StringLike = { "kms:ViaService" = "s3.*.amazonaws.com" } }
    }]
  })
}
