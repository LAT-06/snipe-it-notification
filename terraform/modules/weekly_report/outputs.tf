output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_invoke_arn" {
  value = aws_lambda_function.this.invoke_arn
}

output "event_rule_name" {
  value = aws_cloudwatch_event_rule.this.name
}
