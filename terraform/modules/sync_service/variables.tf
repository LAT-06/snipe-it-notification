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

variable "rest_api_id" {
  type = string
}

variable "root_resource_id" {
  type = string
}

variable "path_part" {
  type = string
}

variable "execution_arn" {
  type = string
}

variable "lambda_permission_statement_id" {
  type = string
}

variable "api_key_required" {
  type    = bool
  default = true
}
