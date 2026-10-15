# Trap: the wildcard is hidden in a variable default.
variable "runtime_policy_json" {
  type    = string
  default = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"*\",\"Resource\":\"*\"}]}"
}

resource "aws_iam_policy" "runtime" {
  name   = "runtime"
  policy = var.runtime_policy_json
}
