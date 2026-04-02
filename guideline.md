# Setup Deploy New Feature Guideline For Admin

## 1. Purpose

This guideline is for a new admin who pulls this repository and wants to deploy using their own AWS credentials.

It covers:

1. IAM access requirements.
2. Local setup.
3. Deployment without manually typing Terraform variables.
4. How to get API endpoints and API key value.
5. How to upload endpoint and API key to APILib Script Properties.

## 2. Prerequisites

Required tools:

1. AWS CLI
2. Terraform version 1.6 or higher
3. Permission to deploy this stack (see docs/minimal-deploy-policy.json)

Check quickly:

    aws --version
    terraform -version

## 3. AWS Credential Setup For New Admin

Configure AWS CLI with your own user credentials:

    aws configure

Enter:

1. AWS Access Key ID
2. AWS Secret Access Key
3. Default region (example: ap-southeast-1)
4. Default output format (json)

Verify active identity:

    aws sts get-caller-identity

You should see your own account and ARN.

## 4. Pull Repository

    git clone <your-repo-url>
    cd Snipe-It-Notification

If already cloned:

    git pull

## 5. Create .env Once (No Manual Terraform Prompt)

Create a file named .env at repository root.

Example:

    SNIPEIT_BASE_URL=https://your-snipeit-domain
    SNIPEIT_API_TOKEN=your-snipeit-token
    GOOGLE_CHAT_WEBHOOK=https://chat.googleapis.com/v1/spaces/...

    AWS_REGION=ap-southeast-1
    PROJECT_NAME=snipeit-notification
    API_STAGE_NAME=prod
    WEEKLY_SCHEDULE_EXPRESSION=cron(0 2 ? * MON *)
    DEPLOYED_STATUS_NAMES=Deployed,In Use
    AVAILABLE_STATUS_NAMES=Ready,Available
    USER_DEFAULT_PASSWORD=ChangeMe@123456

Important:

1. Do not commit .env to git.
2. The deploy script generates terraform/terraform.auto.tfvars from .env automatically.
3. This is why Terraform can run without asking you to type variables.

## 6. Deploy Command (No Interactive Input)

Run one command:

    ./scripts/deploy_infra.sh

What this command already does:

1. Reads .env
2. Creates terraform/terraform.auto.tfvars
3. Runs terraform init -upgrade
4. Auto-imports existing resources if found
5. Runs terraform apply -auto-approve
6. Prints Terraform outputs
7. Prints API key value

## 7. Get Endpoints and API Key After Deploy

The script already prints them. If you need to re-check later:

Get outputs:

    cd terraform
    terraform output

Common endpoint outputs:

1. import_api_url
2. users_sync_api_url
3. categories_sync_api_url
4. locations_sync_api_url
5. manufacturers_sync_api_url
6. statuslabels_sync_api_url
7. suppliers_sync_api_url

Get API key value:

    API_KEY_ID=$(terraform output -raw api_key_id)
    aws apigateway get-api-key --region ap-southeast-1 --api-key "$API_KEY_ID" --include-value --query value --output text

If region is different, replace ap-southeast-1.

## 8. Upload Endpoint and API Key To APILib

Open APILib project in Google Apps Script, then set Script Properties.

Go to:

Project Settings -> Script Properties

Set these keys:

1. API_Key = value from AWS API key command
2. API_Endpoint_assets = import_api_url
3. API_Endpoint_users = users_sync_api_url
4. API_Endpoint_categories = categories_sync_api_url
5. API_Endpoint_locations = locations_sync_api_url
6. API_Endpoint_manufacturers = manufacturers_sync_api_url
7. API_Endpoint_statuslabels = statuslabels_sync_api_url
8. API_Endpoint_suppliers = suppliers_sync_api_url

Then publish APILib version:

1. Deploy
2. Manage deployments
3. Edit deployment
4. New version
5. Deploy

Then update APILib version in each consumer Apps Script project.

## 9. Deploy New Feature In Future

When new handler or endpoint is added by development:

1. Pull latest code.
2. Update .env only if new env input is required.
3. Run deploy script again:

    ./scripts/deploy_infra.sh

4. Read fresh outputs and update APILib Script Properties if endpoint list changed.

## 10. Troubleshooting

If deploy fails due to access denied:

1. Check IAM policy attached to your user or role.
2. Compare with docs/minimal-deploy-policy.json.
3. Confirm permission boundary or organization SCP is not blocking actions.

If Terraform asks for variable input:

1. Check .env exists at repository root.
2. Check required keys are present in .env.
3. Re-run deploy script instead of running raw terraform apply.

If API calls from Apps Script fail after deploy:

1. Verify APILib Script Properties were updated.
2. Verify APILib deployment version was republished.
3. Verify consumer Apps Script is using latest APILib version.

## 11. Security Notes

1. Keep .env local only.
2. Do not share API key publicly.
3. Rotate Snipe-IT token and API key periodically.
4. Runtime secrets are stored in AWS Secrets Manager as one JSON secret bundle.
