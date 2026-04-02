# Snipe-IT Notification Technical Report

## 1. Executive Summary

This system automates Snipe-IT data synchronization and reporting from Google Sheets to AWS.

Current delivered capabilities:

- Asset import and optional checkout from sheet data.
- Entity synchronization for users, categories, locations, manufacturers, status labels, and suppliers.
- Weekly status reporting to Google Chat.
- API Gateway protection with API key.
- Runtime secrets centralized in AWS Secrets Manager (single JSON bundle).
- Terraform refactored into service modules for maintainability.

## 2. Scope

### In Scope

- Google Apps Script clients for manual sync from sheets.
- API Gateway REST endpoints with Lambda proxy integration.
- Lambda handlers for import/sync/report workflows.
- EventBridge weekly schedule for reporting.
- Terraform provisioning and one-command deployment script.

### Out of Scope

- End-to-end lifecycle workflows beyond current sync/report operations.
- Historical analytics warehouse and dashboarding.
- Full idempotency and transactional rollback for batch imports.

## 3. Architecture

### Components

- Google Sheets: operational source input.
- Apps Script: trigger and payload sender.
- API Gateway: secured ingress for sync APIs.
- Lambda services: domain-specific processors.
- Snipe-IT REST API: system of record.
- Google Chat webhook: notification sink.
- EventBridge: weekly report scheduler.
- Secrets Manager: runtime secret bundle.

### High-Level Flow

```text
Google Sheets -> Apps Script -> API Gateway -> Lambda Handlers -> Snipe-IT
                                                    \-> Google Chat

EventBridge (weekly) -> weekly_report Lambda -> Snipe-IT -> Google Chat
```

### Diagram Files

- [assets/architecture.xml](assets/architecture.xml)
- [assets/sequence.xml](assets/sequence.xml)

## 4. API Surface

Current API endpoints:

- POST /import
- POST /users-sync
- POST /categories-sync
- POST /locations-sync
- POST /manufacturers-sync
- POST /statuslabels-sync
- POST /suppliers-sync

Auth model:

- API key required via x-api-key header.

Behavior model:

- 400 for missing required payload sections.
- 200 with partial-failure details for row-level processing errors.

## 5. Processing Flows

### 5.1 Asset Import Flow

1. Apps Script reads active sheet rows and headers.
2. Sends payload to POST /import with batch metadata.
3. Lambda import_handler processes each row independently.
4. Handler resolves reference IDs in Snipe-IT (model, status, location, user).
5. Creates asset and optionally performs checkout.
6. Aggregates status distribution and posts summary to Google Chat.
7. Returns import statistics and first N errors to Apps Script.

### 5.2 Entity Sync Flows

Users/categories/locations/manufacturers/statuslabels/suppliers use dedicated endpoints and handlers.

Shared behavior:

- Per-row validation and normalized payload building.
- Existing-record detection by business key.
- Summary response with created/updated/skipped/failed counts.

### 5.3 Weekly Report Flow

1. EventBridge runs on weekly cron.
2. weekly_report fetches inventory status counts.
3. Computes deployed ratio and available count.
4. Sends formatted status report to Google Chat.

## 6. Data Contracts

### Common Request Pattern

```json
{
  "rows": [
    {
      "name": "example"
    }
  ]
}
```

Asset import also carries metadata such as batch_id, sheet_name, and timestamp.

### Common Response Pattern

```json
{
  "created": 0,
  "updated": 0,
  "skipped": 0,
  "failed": 0,
  "errors": []
}
```

Exact fields vary by handler (for example import_handler returns imported, checked_out, batch_id).

## 7. Security Model

### Current Controls

- API Gateway API key enforcement.
- Runtime secrets stored in one AWS Secrets Manager JSON secret.
- Lambda reads only SECRETS_BUNDLE_ID from env and fetches secret at runtime.
- Lambda role has scoped read permission to the runtime secret.

### Runtime Secret Bundle

Secret keys currently used:

- snipeit_base_url
- snipeit_api_token
- google_chat_webhook
- user_default_password

### Notes

- Single JSON secret lowers Secrets Manager storage cost versus separate secrets.
- Trade-off: fine-grained secret-level permission and rotation is less granular.

## 8. Infrastructure and Deployment

### Terraform Structure

Terraform was modularized into services:

- modules/iam
- modules/sync_service
- modules/weekly_report

Root Terraform wires shared API Gateway, usage plan, stage, secrets, and service modules.

### State Safety

- Resource address migration was handled using moved blocks to avoid recreation.

### Deployment

- Main script: [scripts/deploy_infra.sh](scripts/deploy_infra.sh)
- Script generates terraform.auto.tfvars, initializes Terraform, imports existing resources if needed, then applies.

## 9. Operations

### Logging and Observability

- CloudWatch Logs for all Lambda handlers.
- Row-level errors are logged with row index and entity context.

### Recommended Alerts

- Lambda error rate sustained above threshold.
- Weekly report execution missing.
- High failed/processed ratio for sync handlers.

## 10. Reliability and Limitations

### Current Reliability Pattern

- Partial success is intentional (row-level isolation).
- Synchronous request-response path from Apps Script to Lambda.

### Known Limitations

- No global idempotency key for repeated batch submissions.
- No retry queue / DLQ buffering yet.
- No long-term historical analytics store.

## 11. IAM Requirement for Mentor Deploy

Mentor does not need root access.

Minimum documented policy is available at:

- [docs/minimal-deploy-policy.json](docs/minimal-deploy-policy.json)

This policy covers required permissions for:

- Lambda
- API Gateway
- EventBridge
- Secrets Manager
- IAM role management for project Lambda role
- iam:PassRole scoped to Lambda service

## 12. Source Files Reference

- [apps_script/assets.gs](apps_script/assets.gs)
- [apps_script/user.gs](apps_script/user.gs)
- [apps_script/categories.gs](apps_script/categories.gs)
- [apps_script/locations.gs](apps_script/locations.gs)
- [apps_script/manufacturers.gs](apps_script/manufacturers.gs)
- [apps_script/statuslabels.gs](apps_script/statuslabels.gs)
- [apps_script/suppliers.gs](apps_script/suppliers.gs)
- [src/common.py](src/common.py)
- [src/import_handler.py](src/import_handler.py)
- [src/weekly_report.py](src/weekly_report.py)
- [src/users_sync_handler.py](src/users_sync_handler.py)
- [src/categories_sync_handler.py](src/categories_sync_handler.py)
- [src/locations_sync_handler.py](src/locations_sync_handler.py)
- [src/manufacturers_sync_handler.py](src/manufacturers_sync_handler.py)
- [src/statuslabels_sync_handler.py](src/statuslabels_sync_handler.py)
- [src/suppliers_sync_handler.py](src/suppliers_sync_handler.py)
- [terraform/main.tf](terraform/main.tf)
- [terraform/moved.tf](terraform/moved.tf)
- [terraform/variables.tf](terraform/variables.tf)
- [terraform/outputs.tf](terraform/outputs.tf)
