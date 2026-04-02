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

resource "aws_cloudwatch_event_rule" "this" {
  name                = var.rule_name
  description         = var.rule_description
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "this" {
  rule      = aws_cloudwatch_event_rule.this.name
  target_id = var.target_id
  arn       = aws_lambda_function.this.arn
}

resource "aws_lambda_permission" "allow_events" {
  statement_id  = var.lambda_permission_statement_id
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.this.arn
}
