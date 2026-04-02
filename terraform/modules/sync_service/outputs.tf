output "resource_id" {
  value = aws_api_gateway_resource.this.id
}

output "method_id" {
  value = aws_api_gateway_method.post.id
}

output "integration_id" {
  value = aws_api_gateway_integration.lambda_proxy.id
}

output "function_name" {
  value = aws_lambda_function.this.function_name
}
