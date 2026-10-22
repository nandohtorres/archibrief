# The existing source bucket uses the AWS-managed S3 KMS key. Checksum-enabled
# version HEAD and content writes need these permissions as well as S3 access.
data "aws_kms_alias" "source" {
  name = "alias/aws/s3"
}

resource "aws_iam_role_policy" "admission_storage_key" {
  for_each = {
    upload  = aws_iam_role.create_upload.name
    submit  = aws_iam_role.submit_review.name
    clarify = aws_iam_role.clarify_review.name
    deeper  = aws_iam_role.deeper_review.name
  }
  role = each.value
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = each.key == "deeper" ? ["kms:Decrypt"] : ["kms:Decrypt", "kms:GenerateDataKey"]
      Resource = data.aws_kms_alias.source.target_key_arn
      Condition = { StringLike = { "kms:ViaService" = "s3.*.amazonaws.com" } }
    }]
  })
}
