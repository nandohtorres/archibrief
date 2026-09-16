variable "bucket_name" {
  type        = string
  description = "Name of the immutable source-of-truth bucket (ADR-0007/0042)."
}

variable "tags" {
  type    = map(string)
  default = {}
}
