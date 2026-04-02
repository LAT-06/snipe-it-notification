import json
from typing import Dict, List, Optional

from common import SnipeITClient, load_runtime_config


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _str(value: object) -> str:
    return str(value or "").strip()


def _bool_to_int(value: object) -> Optional[int]:
    s = str(value or "").strip().lower()
    if s in {"1", "true", "yes", "y", "on", "enabled"}:
        return 1
    if s in {"0", "false", "no", "n", "off", "disabled"}:
        return 0
    return None


def _normalize_status_type(value: object) -> str:
    raw = _str(value).lower()
    mapping = {
        "deployable": "deployable",
        "pending": "pending",
        "archived": "archived",
        "undeployable": "undeployable",
        "undep": "undeployable",
    }
    if raw not in mapping:
        raise ValueError(
            f"Invalid status type: {value}. Allowed: deployable, pending, archived, undeployable."
        )
    return mapping[raw]


def _find_by_name(client: SnipeITClient, name: str, cache: Dict[str, Optional[dict]]) -> Optional[dict]:
    key = name.lower()
    if key in cache:
        return cache[key]

    rows = client._paginate_rows("/api/v1/statuslabels", search=name)
    for row in rows:
        if _str(row.get("name")).lower() == key:
            cache[key] = row
            return row

    cache[key] = None
    return None


def lambda_handler(event, _context):
    body = event.get("body") if isinstance(event, dict) else event
    if isinstance(body, str):
        body = json.loads(body)
    body = body or {}

    rows: List[dict] = body.get("rows", [])
    if not rows:
        return _response(400, {"message": "rows is required"})

    config = load_runtime_config()
    client = SnipeITClient(config["snipeit_base_url"], config["snipeit_api_token"])
    cache: Dict[str, Optional[dict]] = {}

    summary = {
        "created": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "skipped_details": [],
    }

    for index, row in enumerate(rows, start=2):
        try:
            name = _str(row.get("name"))
            if not name:
                raise ValueError("Status label name is required")

            existing = _find_by_name(client, name, cache)
            if existing:
                summary["skipped"] += 1
                summary["skipped_details"].append(
                    {
                        "row": str(index),
                        "name": name,
                        "reason": f"Already exists (id={existing.get('id')})",
                    }
                )
                continue

            payload = {
                "name": name,
                "type": _normalize_status_type(row.get("status type")),
                "color": _str(row.get("chart color")),
            }

            show_in_nav = _bool_to_int(row.get("show in side nav"))
            default_label = _bool_to_int(row.get("default label"))
            if show_in_nav is not None:
                payload["show_in_nav"] = show_in_nav
            if default_label is not None:
                payload["default_label"] = default_label

            payload = {k: v for k, v in payload.items() if v not in ("", None)}
            client._request("POST", "/api/v1/statuslabels", body=payload)
            summary["created"] += 1

        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(
                {
                    "row": str(index),
                    "name": _str(row.get("name")),
                    "error": str(exc),
                }
            )
            print(f"Statuslabels sync failed at row {index}: {exc}")

    summary["errors"] = summary["errors"][:20]
    summary["skipped_details"] = summary["skipped_details"][:20]
    return _response(200, summary)
