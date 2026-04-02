variable "function_name" {
  type = string
}

variable "role_arn" {
  type = string
}

variable "runtime" {
  type    = string
  default = "python3.12"
}

variable "handler" {
  type = string
}

variable "filename" {
  type = string
}

variable "source_code_hash" {
  type = string
}

variable "timeout" {
  type = number
}

variable "memory_size" {
  type = number
}

variable "environment" {
  type = map(string)
}

variable "rule_name" {
  type = string
}

variable "rule_description" {
  type = string
  default = null
}

variable "schedule_expression" {
  type = string
}

variable "target_id" {
  type = string
  default = null
}

variable "lambda_permission_statement_id" {
  type = string
}
