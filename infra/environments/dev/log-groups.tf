# Lambda created this group on the function's first run, with no expiry.
# The import adopts it so Terraform sets its retention instead of failing to
# create a duplicate. Remove this block once it has been applied.
import {
  to = module.api_gateway.aws_cloudwatch_log_group.lambda["submit_review"]
  id = "/aws/lambda/archibrief-dev-submit-review"
}
