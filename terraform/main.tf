locals {
  common_env = {
    SECRETS_BUNDLE_ID               = aws_secretsmanager_secret.runtime_bundle.arn
    DEPLOYED_STATUS_NAMES           = join(",", var.deployed_status_names)
    AVAILABLE_STATUS_NAMES          = join(",", var.available_status_names)
    ASSET_REPLACEMENT_AGE_YEARS     = tostring(var.asset_replacement_age_years)
    WARRANTY_EXPIRY_LOOKAHEAD_DAYS  = tostring(var.warranty_expiry_lookahead_days)
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/lambda.zip"
}

module "iam" {
  source    = "./modules/iam"
  role_name = "${var.project_name}-lambda-role"
}

resource "aws_secretsmanager_secret" "runtime_bundle" {
  name                    = "${var.project_name}/runtime"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "runtime_bundle" {
  secret_id = aws_secretsmanager_secret.runtime_bundle.id
  secret_string = jsonencode({
    snipeit_base_url      = var.snipeit_base_url
    snipeit_api_token     = var.snipeit_api_token
    google_chat_webhook   = var.google_chat_webhook
    user_default_password = var.user_default_password
  })
}

resource "aws_iam_role_policy" "lambda_secrets_access" {
  name = "${var.project_name}-lambda-secrets-access"
  role = module.iam.role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadRuntimeBundle"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.runtime_bundle.arn,
        ]
      }
    ]
  })
}

resource "aws_api_gateway_rest_api" "import_api" {
  name = "${var.project_name}-api"
}

module "import_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-import-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "import_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 120
  memory_size                    = 512
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "import"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayImport"
}

module "users_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-users-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "users_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 120
  memory_size                    = 512
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "users-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayUsersSync"
}

module "categories_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-categories-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "categories_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 90
  memory_size                    = 256
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "categories-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayCategoriesSync"
}

module "locations_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-locations-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "locations_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 90
  memory_size                    = 256
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "locations-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayLocationsSync"
}

module "manufacturers_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-manufacturers-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "manufacturers_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 90
  memory_size                    = 256
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "manufacturers-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayManufacturersSync"
}

module "statuslabels_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-statuslabels-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "statuslabels_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 90
  memory_size                    = 256
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "statuslabels-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewayStatuslabelsSync"
}

module "suppliers_sync" {
  source = "./modules/sync_service"

  function_name                  = "${var.project_name}-suppliers-sync-handler"
  role_arn                       = module.iam.role_arn
  handler                        = "suppliers_sync_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 90
  memory_size                    = 256
  environment                    = local.common_env
  rest_api_id                    = aws_api_gateway_rest_api.import_api.id
  root_resource_id               = aws_api_gateway_rest_api.import_api.root_resource_id
  path_part                      = "suppliers-sync"
  execution_arn                  = aws_api_gateway_rest_api.import_api.execution_arn
  lambda_permission_statement_id = "AllowExecutionFromApiGatewaySuppliersSync"
}

module "weekly_report" {
  source = "./modules/weekly_report"

  function_name                  = "${var.project_name}-weekly-report"
  role_arn                       = module.iam.role_arn
  handler                        = "weekly_report.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  timeout                        = 60
  memory_size                    = 256
  environment                    = local.common_env
  rule_name                      = "${var.project_name}-weekly-report"
  rule_description               = null
  schedule_expression            = var.weekly_schedule_expression
  target_id                      = null
  lambda_permission_statement_id = "AllowExecutionFromEventBridgeWeekly"
}

resource "aws_api_gateway_deployment" "import_api" {
  rest_api_id = aws_api_gateway_rest_api.import_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      module.import_sync.resource_id,
      module.users_sync.resource_id,
      module.categories_sync.resource_id,
      module.locations_sync.resource_id,
      module.manufacturers_sync.resource_id,
      module.statuslabels_sync.resource_id,
      module.suppliers_sync.resource_id,
      module.import_sync.method_id,
      module.users_sync.method_id,
      module.categories_sync.method_id,
      module.locations_sync.method_id,
      module.manufacturers_sync.method_id,
      module.statuslabels_sync.method_id,
      module.suppliers_sync.method_id,
      module.import_sync.integration_id,
      module.users_sync.integration_id,
      module.categories_sync.integration_id,
      module.locations_sync.integration_id,
      module.manufacturers_sync.integration_id,
      module.statuslabels_sync.integration_id,
      module.suppliers_sync.integration_id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.import_api.id
  deployment_id = aws_api_gateway_deployment.import_api.id
  stage_name    = var.api_stage_name
}

resource "aws_api_gateway_api_key" "import_key" {
  name = "${var.project_name}-import-key"
}

resource "aws_api_gateway_usage_plan" "import_plan" {
  name = "${var.project_name}-usage-plan"

  api_stages {
    api_id = aws_api_gateway_rest_api.import_api.id
    stage  = aws_api_gateway_stage.prod.stage_name
  }
}

resource "aws_api_gateway_usage_plan_key" "import_key" {
  key_id        = aws_api_gateway_api_key.import_key.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.import_plan.id
}
