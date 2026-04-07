from common import (
    SnipeITClient,
    build_lifecycle_alert_lines,
    build_report_text,
    load_int_from_env,
    load_runtime_config,
    load_status_list_from_env,
    send_google_chat_message,
    utc_now_iso,
)


def lambda_handler(_event, _context):
    config = load_runtime_config()
    snipeit_url = config["snipeit_base_url"]
    snipeit_token = config["snipeit_api_token"]
    chat_webhook = config["google_chat_webhook"]

    deployed_statuses = load_status_list_from_env("DEPLOYED_STATUS_NAMES", ["Deployed", "In Use"])
    available_statuses = load_status_list_from_env("AVAILABLE_STATUS_NAMES", ["Ready", "Available"])
    replacement_age_years = load_int_from_env("ASSET_REPLACEMENT_AGE_YEARS", 3, min_value=1)
    warranty_expiry_lookahead_days = load_int_from_env("WARRANTY_EXPIRY_LOOKAHEAD_DAYS", 30, min_value=1)

    client = SnipeITClient(snipeit_url, snipeit_token)
    total, status_counts, asset_tags_by_status = client.fetch_asset_status_details()
    warranty_due, warranty_expired, replacement_due = client.fetch_asset_lifecycle_alerts(
        deployed_status_names=deployed_statuses,
        replacement_age_years=replacement_age_years,
        warranty_expiry_lookahead_days=warranty_expiry_lookahead_days,
    )

    extra_lines = [f"Generated at: {utc_now_iso()}", ""]
    extra_lines.extend(
        build_lifecycle_alert_lines(
            warranty_due=warranty_due,
            warranty_expired=warranty_expired,
            replacement_due=replacement_due,
            replacement_age_years=replacement_age_years,
            warranty_expiry_lookahead_days=warranty_expiry_lookahead_days,
            max_items_per_section=20,
        )
    )

    text = build_report_text(
        title="Snipe-IT Weekly Report",
        total=total,
        status_counts=status_counts,
        deployed_status_names=deployed_statuses,
        available_status_names=available_statuses,
        detailed_asset_tags_by_status=asset_tags_by_status,
        status_detail_exclude_names=deployed_statuses,
        max_asset_tags_per_status=20,
        extra_lines=extra_lines,
    )

    send_google_chat_message(chat_webhook, text)

    return {
        "statusCode": 200,
        "body": "ok",
    }
