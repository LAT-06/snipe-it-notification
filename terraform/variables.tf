variable "aws_region" {
  type    = string
  default = "ap-southeast-1"
}

variable "project_name" {
  type    = string
  default = "snipeit-notification"
}

variable "snipeit_base_url" {
  type = string
}

variable "snipeit_api_token" {
  type      = string
  sensitive = true
}

variable "google_chat_webhook" {
  type      = string
  sensitive = true
}

variable "user_default_password" {
  type      = string
  sensitive = true
  default   = "ChangeMe@123456"
}

variable "deployed_status_names" {
  type    = list(string)
  default = ["Deployed", "In Use"]
}

variable "available_status_names" {
  type    = list(string)
  default = ["Ready", "Available"]
}

variable "weekly_schedule_expression" {
  type    = string
  default = "cron(0 2 ? * MON *)"
}

variable "api_stage_name" {
  type    = string
  default = "prod"
}
