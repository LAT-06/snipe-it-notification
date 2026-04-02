output "import_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/import"
}

output "users_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/users-sync"
}

output "categories_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/categories-sync"
}

output "locations_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/locations-sync"
}

output "manufacturers_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/manufacturers-sync"
}

output "statuslabels_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/statuslabels-sync"
}

output "suppliers_sync_api_url" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/suppliers-sync"
}

output "api_key_id" {
  value = aws_api_gateway_api_key.import_key.id
}

output "weekly_rule_name" {
  value = module.weekly_report.event_rule_name
}

output "runtime_secret_arn" {
  value = aws_secretsmanager_secret.runtime_bundle.arn
}
