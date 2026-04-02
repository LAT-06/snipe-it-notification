moved {
  from = aws_iam_role.lambda_role
  to   = module.iam.aws_iam_role.lambda_role
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic
  to   = module.iam.aws_iam_role_policy_attachment.lambda_basic
}

moved {
  from = aws_lambda_function.import_handler
  to   = module.import_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.import
  to   = module.import_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.import_post
  to   = module.import_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.import_lambda
  to   = module.import_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_import
  to   = module.import_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.users_sync_handler
  to   = module.users_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.users_sync
  to   = module.users_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.users_sync_post
  to   = module.users_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.users_sync_lambda
  to   = module.users_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_users_sync
  to   = module.users_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.categories_sync_handler
  to   = module.categories_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.categories_sync
  to   = module.categories_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.categories_sync_post
  to   = module.categories_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.categories_sync_lambda
  to   = module.categories_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_categories_sync
  to   = module.categories_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.locations_sync_handler
  to   = module.locations_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.locations_sync
  to   = module.locations_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.locations_sync_post
  to   = module.locations_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.locations_sync_lambda
  to   = module.locations_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_locations_sync
  to   = module.locations_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.manufacturers_sync_handler
  to   = module.manufacturers_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.manufacturers_sync
  to   = module.manufacturers_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.manufacturers_sync_post
  to   = module.manufacturers_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.manufacturers_sync_lambda
  to   = module.manufacturers_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_manufacturers_sync
  to   = module.manufacturers_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.statuslabels_sync_handler
  to   = module.statuslabels_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.statuslabels_sync
  to   = module.statuslabels_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.statuslabels_sync_post
  to   = module.statuslabels_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.statuslabels_sync_lambda
  to   = module.statuslabels_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_statuslabels_sync
  to   = module.statuslabels_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.suppliers_sync_handler
  to   = module.suppliers_sync.aws_lambda_function.this
}

moved {
  from = aws_api_gateway_resource.suppliers_sync
  to   = module.suppliers_sync.aws_api_gateway_resource.this
}

moved {
  from = aws_api_gateway_method.suppliers_sync_post
  to   = module.suppliers_sync.aws_api_gateway_method.post
}

moved {
  from = aws_api_gateway_integration.suppliers_sync_lambda
  to   = module.suppliers_sync.aws_api_gateway_integration.lambda_proxy
}

moved {
  from = aws_lambda_permission.allow_api_gateway_suppliers_sync
  to   = module.suppliers_sync.aws_lambda_permission.allow_api_gateway
}

moved {
  from = aws_lambda_function.weekly_report
  to   = module.weekly_report.aws_lambda_function.this
}

moved {
  from = aws_cloudwatch_event_rule.weekly_report
  to   = module.weekly_report.aws_cloudwatch_event_rule.this
}

moved {
  from = aws_cloudwatch_event_target.weekly_report
  to   = module.weekly_report.aws_cloudwatch_event_target.this
}

moved {
  from = aws_lambda_permission.allow_eventbridge_weekly
  to   = module.weekly_report.aws_lambda_permission.allow_events
}
