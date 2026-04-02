import json
from typing import Dict, List, Optional

from common import SnipeITClient, load_runtime_config


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _bool_to_int(value: object) -> Optional[int]:
    s = str(value or "").strip().lower()
    if s in {"1", "true", "yes", "y", "active", "on", "enabled"}:
        return 1
    if s in {"0", "false", "no", "n", "inactive", "off", "disabled"}:
        return 0
    return None


def _str(value: object) -> str:
    return str(value or "").strip()


def _find_user_by_email_or_username(client: SnipeITClient, email: str, username: str) -> Optional[dict]:
    q = email or username
    if not q:
        return None

    result = client._request("GET", "/api/v1/users", query={"search": q, "limit": 100, "offset": 0})
    rows = result.get("rows", [])

    email_l = email.lower()
    username_l = username.lower()
    for row in rows:
        row_email = _str(row.get("email")).lower()
        row_username = _str(row.get("username")).lower()
        if (email_l and row_email == email_l) or (username_l and row_username == username_l):
            return row

    for row in client._paginate_rows("/api/v1/users"):
        row_email = _str(row.get("email")).lower()
        row_username = _str(row.get("username")).lower()
        if (email_l and row_email == email_l) or (username_l and row_username == username_l):
            return row

    return None


def _resolve_id_by_name(client: SnipeITClient, path: str, name: str, cache: Dict[str, Optional[int]]) -> Optional[int]:
    key = name.strip().lower()
    if not key:
        return None
    if key in cache:
        return cache[key]

    rows = client._paginate_rows(path, search=name)
    for row in rows:
        if _str(row.get("name")).lower() == key:
            cache[key] = int(row["id"])
            return cache[key]

    cache[key] = None
    return None


def _build_payload(
    *,
    row: dict,
    client: SnipeITClient,
    location_cache: Dict[str, Optional[int]],
    company_cache: Dict[str, Optional[int]],
) -> dict:
    payload = {
        "first_name": _str(row.get("First Name")),
        "last_name": _str(row.get("Last Name")),
        "email": _str(row.get("Email")),
        "username": _str(row.get("Username")),
        "employee_num": _str(row.get("Employee Number")),
        "jobtitle": _str(row.get("Job Title")),
        "phone": _str(row.get("Phone")),
        "website": _str(row.get("Website")),
        "address": _str(row.get("Address")),
        "city": _str(row.get("City")),
        "state": _str(row.get("State")),
        "country": _str(row.get("Country")),
        "zip": _str(row.get("Postal Code")),
        "notes": _str(row.get("Notes")),
        "start_date": _str(row.get("Start Date")),
        "end_date": _str(row.get("End Date")),
    }

    activated = _bool_to_int(row.get("Activated"))
    remote = _bool_to_int(row.get("Remote"))
    vip = _bool_to_int(row.get("VIP"))
    gravatar = _bool_to_int(row.get("Gravatar"))

    if activated is not None:
        payload["activated"] = activated
    if remote is not None:
        payload["remote"] = remote
    if vip is not None:
        payload["vip"] = vip
    if gravatar is not None:
        payload["gravatar"] = gravatar

    location_name = _str(row.get("Location"))
    if location_name:
        location_id = _resolve_id_by_name(client, "/api/v1/locations", location_name, location_cache)
        if location_id:
            payload["location_id"] = location_id

    company_name = _str(row.get("Company"))
    if company_name:
        company_id = _resolve_id_by_name(client, "/api/v1/companies", company_name, company_cache)
        if company_id:
            payload["company_id"] = company_id

    manager_identity = _str(row.get("Manager"))
    if manager_identity:
        manager = _find_user_by_email_or_username(
            client,
            email=manager_identity if "@" in manager_identity else "",
            username="" if "@" in manager_identity else manager_identity,
        )
        if manager:
            payload["manager_id"] = int(manager["id"])

    return {k: v for k, v in payload.items() if v not in ("", None)}


def lambda_handler(event, _context):
    body = event.get("body") if isinstance(event, dict) else event
    if isinstance(body, str):
        body = json.loads(body)
    body = body or {}

    rows: List[dict] = body.get("rows", [])
    create_if_missing = bool(body.get("create_if_missing", True))

    if not rows:
        return _response(400, {"message": "rows is required"})

    config = load_runtime_config()
    client = SnipeITClient(config["snipeit_base_url"], config["snipeit_api_token"])
    default_password = config.get("user_default_password") or "ChangeMe@123456"

    location_cache: Dict[str, Optional[int]] = {}
    company_cache: Dict[str, Optional[int]] = {}

    summary = {
        "updated": 0,
        "created": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "skipped_details": [],
    }

    for index, row in enumerate(rows, start=2):
        try:
            email = _str(row.get("Email"))
            username = _str(row.get("Username"))
            if not email and not username:
                raise ValueError("Email or Username is required")

            existing = _find_user_by_email_or_username(client, email=email, username=username)
            payload = _build_payload(
                row=row,
                client=client,
                location_cache=location_cache,
                company_cache=company_cache,
            )

            if existing:
                client._request("PUT", f"/api/v1/users/{existing['id']}", body=payload)
                summary["updated"] += 1
                continue

            if not create_if_missing:
                summary["skipped"] += 1
                summary["skipped_details"].append(
                    {
                        "row": str(index),
                        "email": email,
                        "username": username,
                        "reason": "User not found in Snipe-IT",
                    }
                )
                continue

            if not payload.get("first_name"):
                raise ValueError("First Name is required for create")
            if not payload.get("username"):
                raise ValueError("Username is required for create")

            payload["password"] = default_password
            payload["password_confirmation"] = default_password
            client._request("POST", "/api/v1/users", body=payload)
            summary["created"] += 1

        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(
                {
                    "row": str(index),
                    "email": _str(row.get("Email")),
                    "username": _str(row.get("Username")),
                    "error": str(exc),
                }
            )
            print(f"Users sync failed at row {index}: {exc}")

    summary["errors"] = summary["errors"][:20]
    summary["skipped_details"] = summary["skipped_details"][:20]
    return _response(200, summary)
