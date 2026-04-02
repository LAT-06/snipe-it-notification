#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT_DIR/terraform"

if ! command -v terraform >/dev/null 2>&1; then
  echo "[ERROR] terraform is required"
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "[ERROR] aws cli is required"
  exit 1
fi

# Load local environment from .env if present.
if [[ -f "$ROOT_DIR/.env" ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ROOT_DIR/.env" | xargs)
fi

: "${SNIPEIT_BASE_URL:?Missing SNIPEIT_BASE_URL}"
: "${SNIPEIT_API_TOKEN:?Missing SNIPEIT_API_TOKEN}"
: "${GOOGLE_CHAT_WEBHOOK:?Missing GOOGLE_CHAT_WEBHOOK}"

AWS_REGION="${AWS_REGION:-ap-southeast-1}"
PROJECT_NAME="${PROJECT_NAME:-snipeit-notification}"
API_STAGE_NAME="${API_STAGE_NAME:-prod}"
WEEKLY_SCHEDULE_EXPRESSION="${WEEKLY_SCHEDULE_EXPRESSION:-cron(0 2 ? * MON *)}"
DEPLOYED_STATUS_NAMES="${DEPLOYED_STATUS_NAMES:-Deployed,In Use}"
AVAILABLE_STATUS_NAMES="${AVAILABLE_STATUS_NAMES:-Ready,Available}"
USER_DEFAULT_PASSWORD="${USER_DEFAULT_PASSWORD:-ChangeMe@123456}"

split_csv_to_hcl_list() {
  local input="$1"
  local IFS=','
  read -ra parts <<<"$input"
  local out=""
  for p in "${parts[@]}"; do
    p="$(echo "$p" | sed 's/^ *//;s/ *$//')"
    if [[ -n "$p" ]]; then
      if [[ -n "$out" ]]; then out+=" ,"; fi
      out+="\"$p\""
    fi
  done
  echo "$out"
}

DEPLOYED_HCL="$(split_csv_to_hcl_list "$DEPLOYED_STATUS_NAMES")"
AVAILABLE_HCL="$(split_csv_to_hcl_list "$AVAILABLE_STATUS_NAMES")"

cat >"$TF_DIR/terraform.auto.tfvars" <<EOF
aws_region                  = "$AWS_REGION"
project_name                = "$PROJECT_NAME"
snipeit_base_url            = "$SNIPEIT_BASE_URL"
snipeit_api_token           = "$SNIPEIT_API_TOKEN"
google_chat_webhook         = "$GOOGLE_CHAT_WEBHOOK"
user_default_password       = "$USER_DEFAULT_PASSWORD"
weekly_schedule_expression  = "$WEEKLY_SCHEDULE_EXPRESSION"
api_stage_name              = "$API_STAGE_NAME"
deployed_status_names       = [$DEPLOYED_HCL]
available_status_names      = [$AVAILABLE_HCL]
EOF

cd "$TF_DIR"
terraform init -upgrade

import_if_missing() {
  local addr="$1"
  local import_id="$2"

  if terraform state show "$addr" >/dev/null 2>&1; then
    echo "[INFO] State already has $addr"
    return
  fi

  echo "[INFO] Importing $addr <- $import_id"
  terraform import "$addr" "$import_id" >/dev/null
}

# Auto-import only when resources already exist (avoid manual import steps).
REST_API_ID="$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='${PROJECT_NAME}-api'].id | [0]" --output text 2>/dev/null || true)"
if [[ "$REST_API_ID" != "None" && -n "$REST_API_ID" ]]; then
  USERS_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='users-sync'].id | [0]" --output text 2>/dev/null || true)"
  CATEGORIES_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='categories-sync'].id | [0]" --output text 2>/dev/null || true)"
  LOCATIONS_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='locations-sync'].id | [0]" --output text 2>/dev/null || true)"
  MANUFACTURERS_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='manufacturers-sync'].id | [0]" --output text 2>/dev/null || true)"
  STATUSLABELS_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='statuslabels-sync'].id | [0]" --output text 2>/dev/null || true)"
  SUPPLIERS_RESOURCE_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='suppliers-sync'].id | [0]" --output text 2>/dev/null || true)"

  if [[ "$USERS_RESOURCE_ID" != "None" && -n "$USERS_RESOURCE_ID" ]]; then
    import_if_missing "module.users_sync.aws_api_gateway_resource.this" "$REST_API_ID/$USERS_RESOURCE_ID"
  fi
  if [[ "$CATEGORIES_RESOURCE_ID" != "None" && -n "$CATEGORIES_RESOURCE_ID" ]]; then
    import_if_missing "module.categories_sync.aws_api_gateway_resource.this" "$REST_API_ID/$CATEGORIES_RESOURCE_ID"
  fi
  if [[ "$LOCATIONS_RESOURCE_ID" != "None" && -n "$LOCATIONS_RESOURCE_ID" ]]; then
    import_if_missing "module.locations_sync.aws_api_gateway_resource.this" "$REST_API_ID/$LOCATIONS_RESOURCE_ID"
  fi
  if [[ "$MANUFACTURERS_RESOURCE_ID" != "None" && -n "$MANUFACTURERS_RESOURCE_ID" ]]; then
    import_if_missing "module.manufacturers_sync.aws_api_gateway_resource.this" "$REST_API_ID/$MANUFACTURERS_RESOURCE_ID"
  fi
  if [[ "$STATUSLABELS_RESOURCE_ID" != "None" && -n "$STATUSLABELS_RESOURCE_ID" ]]; then
    import_if_missing "module.statuslabels_sync.aws_api_gateway_resource.this" "$REST_API_ID/$STATUSLABELS_RESOURCE_ID"
  fi
  if [[ "$SUPPLIERS_RESOURCE_ID" != "None" && -n "$SUPPLIERS_RESOURCE_ID" ]]; then
    import_if_missing "module.suppliers_sync.aws_api_gateway_resource.this" "$REST_API_ID/$SUPPLIERS_RESOURCE_ID"
  fi
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-users-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.users_sync.aws_lambda_function.this" "${PROJECT_NAME}-users-sync-handler"
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-categories-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.categories_sync.aws_lambda_function.this" "${PROJECT_NAME}-categories-sync-handler"
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-locations-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.locations_sync.aws_lambda_function.this" "${PROJECT_NAME}-locations-sync-handler"
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-manufacturers-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.manufacturers_sync.aws_lambda_function.this" "${PROJECT_NAME}-manufacturers-sync-handler"
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-statuslabels-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.statuslabels_sync.aws_lambda_function.this" "${PROJECT_NAME}-statuslabels-sync-handler"
fi

if aws lambda get-function --region "$AWS_REGION" --function-name "${PROJECT_NAME}-suppliers-sync-handler" >/dev/null 2>&1; then
  import_if_missing "module.suppliers_sync.aws_lambda_function.this" "${PROJECT_NAME}-suppliers-sync-handler"
fi

terraform apply -auto-approve

echo ""
echo "[INFO] Terraform outputs:"
terraform output

echo ""
echo "[INFO] API key value:"
API_KEY_ID="$(terraform output -raw api_key_id)"
aws apigateway get-api-key --region "$AWS_REGION" --api-key "$API_KEY_ID" --include-value --query 'value' --output text
