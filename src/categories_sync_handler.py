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


def _normalize_category_type(value: object) -> str:
    raw = _str(value).lower()
    mapping = {
        "asset": "asset",
        "accessory": "accessory",
        "consumable": "consumable",
        "component": "component",
        "license": "license",
        "licence": "license",
    }
    if raw not in mapping:
        raise ValueError(
            f"Invalid category type: {value}. Allowed: asset, accessory, consumable, component, license."
        )
    return mapping[raw]


def _find_category(client: SnipeITClient, name: str, category_type: str, cache: Dict[str, Optional[dict]]) -> Optional[dict]:
    key = f"{name.lower()}|{category_type}"
    if key in cache:
        return cache[key]

    result = client._request("GET", "/api/v1/categories", query={"search": name, "limit": 100, "offset": 0})
    rows = result.get("rows", [])
    for row in rows:
        if _str(row.get("name")).lower() == name.lower() and _str(row.get("category_type")).lower() == category_type:
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
                raise ValueError("Category name is required")

            category_type = _normalize_category_type(row.get("category type"))
            existing = _find_category(client, name, category_type, cache)
            if existing:
                summary["skipped"] += 1
                summary["skipped_details"].append(
                    {
                        "row": str(index),
                        "name": name,
                        "reason": f"Already exists (id={existing.get('id')}, type={category_type})",
                    }
                )
                continue

            payload = {
                "name": name,
                "category_type": category_type,
                "notes": _str(row.get("notes")),
                "eula_text": _str(row.get("eula text")),
            }

            require_acceptance = _bool_to_int(row.get("require acceptance"))
            checkin_email = _bool_to_int(row.get("checkin email"))
            use_default_eula = _bool_to_int(row.get("use default eula"))

            if require_acceptance is not None:
                payload["require_acceptance"] = require_acceptance
            if checkin_email is not None:
                payload["checkin_email"] = checkin_email
            if use_default_eula is not None:
                payload["use_default_eula"] = use_default_eula

            payload = {k: v for k, v in payload.items() if v not in ("", None)}
            client._request("POST", "/api/v1/categories", body=payload)
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
            print(f"Categories sync failed at row {index}: {exc}")

    summary["errors"] = summary["errors"][:20]
    summary["skipped_details"] = summary["skipped_details"][:20]
    return _response(200, summary)
