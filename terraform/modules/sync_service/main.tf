resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.role_arn
  runtime          = var.runtime
  handler          = var.handler
  filename         = var.filename
  source_code_hash = var.source_code_hash
  timeout          = var.timeout
  memory_size      = var.memory_size

  environment {
    variables = var.environment
  }
}

resource "aws_api_gateway_resource" "this" {
  rest_api_id = var.rest_api_id
  parent_id   = var.root_resource_id
  path_part   = var.path_part
}

resource "aws_api_gateway_method" "post" {
  rest_api_id      = var.rest_api_id
  resource_id      = aws_api_gateway_resource.this.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "lambda_proxy" {
  rest_api_id             = var.rest_api_id
  resource_id             = aws_api_gateway_resource.this.id
  http_method             = aws_api_gateway_method.post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.this.invoke_arn
}

resource "aws_lambda_permission" "allow_api_gateway" {
  statement_id  = var.lambda_permission_statement_id
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.execution_arn}/*/*"
}
