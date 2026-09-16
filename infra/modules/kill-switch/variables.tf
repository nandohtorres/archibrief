variable "name_prefix" {
  type    = string
  default = "archibrief"
}

variable "kill_switch_default" {
  type    = string
  default = "false"
}

variable "tags" {
  type    = map(string)
  default = {}
}
