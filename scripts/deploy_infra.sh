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
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    # Loại bỏ dấu ngoặc kép bao quanh giá trị nếu có trong file .env để tránh double quote
    line=$(echo "$line" | sed 's/=["'\'']\(.*\)["'\'']$/=\1/')
    export "$line"
  done < "$ROOT_DIR/.env"
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
ASSET_REPLACEMENT_AGE_YEARS="${ASSET_REPLACEMENT_AGE_YEARS:-3}"
WARRANTY_EXPIRY_LOOKAHEAD_DAYS="${WARRANTY_EXPIRY_LOOKAHEAD_DAYS:-30}"

# Hàm xử lý: Chuyển CSV thành định dạng ["a", "b"] cho Terraform
split_csv_to_hcl_list() {
  local input="$1"
  local IFS=','
  read -ra parts <<<"$input"
  local out=""
  for p in "${parts[@]}"; do
    # Trim khoảng trắng thừa
    p=$(echo "$p" | xargs)
    if [[ -n "$p" ]]; then
      [[ -n "$out" ]] && out+=", "
      out+="\"$p\""
    fi
  done
  echo "$out"
}

DEPLOYED_HCL=$(split_csv_to_hcl_list "$DEPLOYED_STATUS_NAMES")
AVAILABLE_HCL=$(split_csv_to_hcl_list "$AVAILABLE_STATUS_NAMES")

# Ghi đè file tfvars (Dùng dấu > để làm mới file mỗi lần chạy)
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
asset_replacement_age_years = $ASSET_REPLACEMENT_AGE_YEARS
warranty_expiry_lookahead_days = $WARRANTY_EXPIRY_LOOKAHEAD_DAYS
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
  terraform import "$addr" "$import_id" >/dev/null || echo "[WARN] Failed to import $addr"
}

# Tự động import Resource API Gateway nếu đã tồn tại
REST_API_ID="$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='${PROJECT_NAME}-api'].id | [0]" --output text 2>/dev/null || true)"

if [[ "$REST_API_ID" != "None" && -n "$REST_API_ID" ]]; then
  # Mảng các resource path cần check
  resources=("users-sync" "categories-sync" "locations-sync" "manufacturers-sync" "statuslabels-sync" "suppliers-sync")
  
  for res in "${resources[@]}"; do
    RES_ID="$(aws apigateway get-resources --region "$AWS_REGION" --rest-api-id "$REST_API_ID" --query "items[?pathPart=='$res'].id | [0]" --output text 2>/dev/null || true)"
    if [[ "$RES_ID" != "None" && -n "$RES_ID" ]]; then
      # Chuyển đổi path-part thành snake_case cho module name (ví dụ: users-sync -> users_sync)
      module_name=$(echo "$res" | sed 's/-/_/g')
      import_if_missing "module.${module_name}.aws_api_gateway_resource.this" "$REST_API_ID/$RES_ID"
    fi
  done
fi

# Tự động import Lambda functions nếu đã tồn tại
functions=("users-sync" "categories-sync" "locations-sync" "manufacturers-sync" "statuslabels-sync" "suppliers-sync")
for func in "${functions[@]}"; do
  func_name="${PROJECT_NAME}-${func}-handler"
  module_name=$(echo "$func" | sed 's/-/_/g')
  if aws lambda get-function --region "$AWS_REGION" --function-name "$func_name" >/dev/null 2>&1; then
    import_if_missing "module.${module_name}.aws_lambda_function.this" "$func_name"
  fi
done

terraform apply -auto-approve

echo -e "\n[INFO] Terraform outputs:"
terraform output

echo -e "\n[INFO] API key value:"
API_KEY_ID="$(terraform output -raw api_key_id)"
aws apigateway get-api-key --region "$AWS_REGION" --api-key "$API_KEY_ID" --include-value --query 'value' --output text