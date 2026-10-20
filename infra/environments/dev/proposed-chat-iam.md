# Proposed deploy-role permissions for the report chat (ADR-0050)

**Not applied. Fernando makes every IAM edit.** The chat deploys without
any of this: the alarms are off by default (`chat_alarms_enabled =
false`), and the Lambdas, routes, table and guardrails only need
permissions the deploy role already has.

The inline policy on the `ArchiBriefDeploy` permission set is at AWS's
10,240-character limit (see `deploy-role-policies-proposed/README.md`),
so these are written as one small customer-managed policy to attach to
the same permission set rather than more inline statements.

## What each statement is for

| Sid | Needed for | When |
|---|---|---|
| `ChatMetricFilters` | Terraform creating the chat log metric filters | Before setting `chat_alarms_enabled = true` |
| `ChatAlarms` | Terraform creating the four chat alarms | Same |
| `ChatEvalInvokeHaiku` | Running the paid chat eval locally with the deploy profile (`python -m backend.chat.chat_eval`) on Haiku 4.5 | Before the first chat eval run |

The eval also needs Titan embeddings, S3 Vectors queries and
`bedrock:ApplyGuardrail`; the existing `BedrockReasoningInvoke`,
`S3VectorsIndex` and `BedrockGuardrails` statements already cover those.

## Policy

Replace `ACCOUNT_ID` with the real account ID when pasting it into the
console. The real ID never goes in a committed file.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ChatMetricFilters",
      "Effect": "Allow",
      "Action": [
        "logs:PutMetricFilter",
        "logs:DeleteMetricFilter",
        "logs:DescribeMetricFilters"
      ],
      "Resource": "arn:aws:logs:us-east-1:ACCOUNT_ID:log-group:/aws/lambda/archibrief-dev-*"
    },
    {
      "Sid": "ChatAlarms",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:ListTagsForResource",
        "cloudwatch:TagResource",
        "cloudwatch:UntagResource"
      ],
      "Resource": "arn:aws:cloudwatch:us-east-1:ACCOUNT_ID:alarm:archibrief-dev-*"
    },
    {
      "Sid": "ChatEvalInvokeHaiku",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:GetInferenceProfile"],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:*:ACCOUNT_ID:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0"
      ]
    }
  ]
}
```

`cloudwatch:DescribeAlarms` is account-wide in practice for listing; if
Terraform's refresh fails on it with the scoped resource, move that one
action into a separate statement with `"Resource": "*"` (it's read-only).
