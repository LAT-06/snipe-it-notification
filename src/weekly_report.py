from common import (
    SnipeITClient,
    build_report_text,
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

    client = SnipeITClient(snipeit_url, snipeit_token)
    total, status_counts = client.fetch_asset_status_counts()

    text = build_report_text(
        title="Snipe-IT Weekly Report",
        total=total,
        status_counts=status_counts,
        deployed_status_names=deployed_statuses,
        available_status_names=available_statuses,
        extra_lines=[f"Generated at: {utc_now_iso()}"],
    )

    send_google_chat_message(chat_webhook, text)

    return {
        "statusCode": 200,
        "body": "ok",
    }
