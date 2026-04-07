# Snipe-IT Notification

This project automates import and reporting for Snipe-IT using:

- Google Sheet + Apps Script clients
- API Gateway protected endpoints
- Lambda handlers for assets/users/categories sync
- Weekly EventBridge reporting to Google Chat

## 1) Architecture Summary

Main paths:

- `POST /import` -> assets sync (`import_handler`)
- `POST /users-sync` -> users sync (`users_sync_handler`)
- `POST /categories-sync` -> categories sync (`categories_sync_handler`)
- `POST /locations-sync` -> locations sync (`locations_sync_handler`)
- `POST /manufacturers-sync` -> manufacturers sync (`manufacturers_sync_handler`)
- `POST /statuslabels-sync` -> status labels sync (`statuslabels_sync_handler`)
- `POST /suppliers-sync` -> suppliers sync (`suppliers_sync_handler`)
- EventBridge weekly cron -> `weekly_report`

## 2) One-Command Infra Deploy

Mentor/lead flow requirement is supported: pull repo, set local environment, then run one script.

Prerequisites:

- Terraform >= 1.6
- AWS CLI configured (`aws sts get-caller-identity` must work)
- Access to deploy in target AWS account

Create `.env` at repository root:

```bash
SNIPEIT_BASE_URL=https://xxxxxxxxx.xxxxxxxxx.com
SNIPEIT_API_TOKEN=replace-with-snipeit-token
GOOGLE_CHAT_WEBHOOK=https://chat.googleapis.com/v1/spaces/...

AWS_REGION=ap-southeast-1
PROJECT_NAME=xxxxxxxxx-notification
API_STAGE_NAME=prod
WEEKLY_SCHEDULE_EXPRESSION=cron(0 2 ? * MON *)
DEPLOYED_STATUS_NAMES=Deployed,In Use
AVAILABLE_STATUS_NAMES=Ready,Available
ASSET_REPLACEMENT_AGE_YEARS=3
WARRANTY_EXPIRY_LOOKAHEAD_DAYS=30
USER_DEFAULT_PASSWORD=ChangeMe@123456
```

Run deploy script:

```bash
./scripts/deploy_infra.sh
```

What this script does:

1. Generates `terraform/terraform.auto.tfvars` from local env
2. Runs `terraform init -upgrade`
3. Auto-imports pre-existing resources (if found) to avoid manual `terraform import`
4. Runs `terraform apply -auto-approve`
5. Prints outputs + current API Gateway key value

Secrets model:

- Terraform stores runtime secrets as one JSON bundle in AWS Secrets Manager (`${project_name}/runtime`)
- Lambda functions receive only `SECRETS_BUNDLE_ID` and fetch/parse the JSON at runtime
- Secret payload keys:
   - `snipeit_base_url`
   - `snipeit_api_token`
   - `google_chat_webhook`
   - `user_default_password`

Notification policy variables:

- `ASSET_REPLACEMENT_AGE_YEARS`: age threshold for replacement candidates (deployed assets only)
- `WARRANTY_EXPIRY_LOOKAHEAD_DAYS`: lookahead window for warranty-expiring alerts

## 3) Terraform Outputs You Need

After apply, these outputs are available:

- `import_api_url`
- `users_sync_api_url`
- `categories_sync_api_url`
- `locations_sync_api_url`
- `manufacturers_sync_api_url`
- `statuslabels_sync_api_url`
- `suppliers_sync_api_url`
- `api_key_id`

## 4) APILib Setup (Shared Apps Script Library)

Apps Script files now read key/endpoints from APILib:

- [apps_script/assets.gs](apps_script/assets.gs)
- [apps_script/user.gs](apps_script/user.gs)
- [apps_script/categories.gs](apps_script/categories.gs)

Expected APILib functions:

```javascript
function getApiKey() {
   return PropertiesService.getScriptProperties().getProperty('API_Key');
}

function getEndpointAssets() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_assets');
}

function getEndpointCategories() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_categories');
}

function getEndpointUsers() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_users');
}

function getEndpointLocations() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_locations');
}

function getEndpointManufacturers() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_manufacturers');
}

function getEndpointStatuslabels() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_statuslabels');
}

function getEndpointSuppliers() {
   return PropertiesService.getScriptProperties().getProperty('API_Endpoint_suppliers');
}
```

### Script Properties in APILib (important)

Set these in the APILib project (not consumer projects):

- `API_Key` = API Gateway key value
- `API_Endpoint_assets` = value of `import_api_url`
- `API_Endpoint_users` = value of `users_sync_api_url`
- `API_Endpoint_categories` = value of `categories_sync_api_url`
- `API_Endpoint_locations` = value of `locations_sync_api_url`
- `API_Endpoint_manufacturers` = value of `manufacturers_sync_api_url`
- `API_Endpoint_statuslabels` = value of `statuslabels_sync_api_url`
- `API_Endpoint_suppliers` = value of `suppliers_sync_api_url`

If lead uses another account, they only need to update these Script Properties in APILib after running deploy.

### APILib release steps

1. Save APILib project
2. Deploy -> Manage deployments -> Edit deployment -> New version -> Deploy
3. In each consumer Apps Script project, update library version to latest

## 5) Sheet Header Requirements

### Assets headers

- Company
- Name
- Asset Tag
- Serial Number
- Category
- Status
- Supplier
- Manufacturer
- Location
- Order Number
- Model
- Model Notes
- Model Number
- Asset Notes
- Purchase Date
- Purchase Cost
- Checkout Type
- Checked Out To: Username
- Checked Out To: First Name
- Checked Out To: Last Name
- Checked Out To: Email
- Checkout to Location
- Warranty
- EOL Date

### Users headers

- First Name
- Last Name
- Email
- Username
- Display Name
- Activated
- Location
- Address
- City
- State
- Country
- Postal Code
- Website
- Phone
- Job Title
- Notes
- Employee Number
- Company
- Manager
- Remote
- VIP
- Start Date
- End Date
- Gravatar

### Categories headers

- name
- category type
- notes
- require acceptance
- checkin email
- use default eula
- eula text

### Locations headers

- name
- address
- address2
- city
- state
- country
- zip
- notes
- phone
- fax
- currency

### Manufacturers headers

- name
- notes
- support phone
- support email
- warranty lookup url
- url

### Status Labels headers

- name
- status type
- assets
- chart color
- show in side nav
- default label

### Suppliers headers

- name
- address
- address2
- city
- state
- country
- zip
- notes
- contact
- phone
- fax

## 6) Operational Notes

- No DB is required for current-state reporting.
- Add DynamoDB only if you need strict idempotency/history/audit at scale.
- Weekly report schedule is controlled by `WEEKLY_SCHEDULE_EXPRESSION`.

## 7) Minimal IAM Deploy Role for Mentor

Mentor does not need root access. They only need an IAM user/role with deploy permissions for this stack.

Use this policy template:

- `docs/minimal-deploy-policy.json`

Before attaching policy, replace placeholders:

- `<AWS_REGION>`
- `<ACCOUNT_ID>`
- `<PROJECT_NAME>`

Example:

- `<AWS_REGION>` -> `ap-southeast-1`
- `<ACCOUNT_ID>` -> `xxxxxxxxxxxxxxx`
- `<PROJECT_NAME>` -> `snipeit-notification`

Notes:

- Policy is scoped to this project prefix only.
- It includes `iam:PassRole` only for `<PROJECT_NAME>-lambda-role` and only to Lambda service.
- If your organization enforces permission boundaries/SCP, make sure they also allow the same actions.
