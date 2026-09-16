variable "table_prefix" {
  type        = string
  description = "Prefix applied to every table name, e.g. \"archibrief-dev\"."
}

variable "tags" {
  type    = map(string)
  default = {}
}
