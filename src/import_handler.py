import json
from typing import Dict, List

from common import (
    SnipeITClient,
    build_report_text,
    load_status_list_from_env,
    load_runtime_config,
    send_google_chat_message,
    utc_now_iso,
)


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, _context):
    body = event.get("body") if isinstance(event, dict) else event
    if isinstance(body, str):
        body = json.loads(body)

    body = body or {}
    rows: List[dict] = body.get("rows", [])
    sheet_name = body.get("sheet_name", "Unknown Sheet")
    batch_id = body.get("batch_id", "no-batch-id")

    if not rows:
        return _response(400, {"message": "rows is required"})

    config = load_runtime_config()
    snipeit_url = config["snipeit_base_url"]
    snipeit_token = config["snipeit_api_token"]
    chat_webhook = config["google_chat_webhook"]

    deployed_statuses = load_status_list_from_env("DEPLOYED_STATUS_NAMES", ["Deployed", "In Use"])
    available_statuses = load_status_list_from_env("AVAILABLE_STATUS_NAMES", ["Ready", "Available"])

    client = SnipeITClient(snipeit_url, snipeit_token)

    imported = 0
    failed = 0
    checked_out = 0
    errors: List[Dict[str, str]] = []
    imported_tags: List[str] = []

    for index, row in enumerate(rows, start=2):
        try:
            asset_id, asset_tag = client.create_asset(row)
            imported += 1
            imported_tags.append(asset_tag)
            if client.checkout_asset(asset_id, row):
                checked_out += 1
        except Exception as exc:
            failed += 1
            errors.append(
                {
                    "row": str(index),
                    "asset_tag": str(row.get("Asset Tag", "")),
                    "error": str(exc),
                }
            )
            print(f"Import failed at row {index}, asset_tag={row.get('Asset Tag', '')}: {exc}")

    total, status_counts = client.fetch_asset_status_counts()

    extra_lines = [
        f"Batch: {batch_id}",
        f"Sheet: {sheet_name}",
        f"Imported successfully: {imported}",
        f"Failed imports: {failed}",
        f"Successful checkouts: {checked_out}",
        f"Time: {utc_now_iso()}",
    ]
    if imported_tags:
        preview = ", ".join(imported_tags[:15])
        suffix = " ..." if len(imported_tags) > 15 else ""
        extra_lines.append(f"New assets: {preview}{suffix}")

    if errors:
        extra_lines.append("Error details (first 5):")
        for item in errors[:5]:
            extra_lines.append(
                f"- Row {item['row']} | Asset Tag: {item['asset_tag'] or 'N/A'} | {item['error']}"
            )

    text = build_report_text(
        title="Snipe-IT Import Summary",
        total=total,
        status_counts=status_counts,
        deployed_status_names=deployed_statuses,
        available_status_names=available_statuses,
        extra_lines=extra_lines,
    )
    send_google_chat_message(chat_webhook, text)

    return _response(
        200,
        {
            "imported": imported,
            "failed": failed,
            "checked_out": checked_out,
            "errors": errors[:20],
            "batch_id": batch_id,
        },
    )
