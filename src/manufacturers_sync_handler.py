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


def _find_by_name(client: SnipeITClient, name: str, cache: Dict[str, Optional[dict]]) -> Optional[dict]:
    key = name.lower()
    if key in cache:
        return cache[key]

    rows = client._paginate_rows("/api/v1/manufacturers", search=name)
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
                raise ValueError("Manufacturer name is required")

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
                "notes": _str(row.get("notes")),
                "support_phone": _str(row.get("support phone")),
                "support_email": _str(row.get("support email")),
                "warranty_lookup_url": _str(row.get("warranty lookup url")),
                "url": _str(row.get("url")),
            }
            payload = {k: v for k, v in payload.items() if v not in ("", None)}

            client._request("POST", "/api/v1/manufacturers", body=payload)
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
            print(f"Manufacturers sync failed at row {index}: {exc}")

    summary["errors"] = summary["errors"][:20]
    summary["skipped_details"] = summary["skipped_details"][:20]
    return _response(200, summary)
