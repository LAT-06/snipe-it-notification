import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import boto3


_RUNTIME_CONFIG_CACHE: Optional[Dict[str, str]] = None


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class HttpError(Exception):
    def __init__(self, status_code: int, payload: str):
        super().__init__(f"HTTP {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload


class SnipeITClient:
    def __init__(self, base_url: str, api_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._status_cache: Dict[str, int] = {}
        self._model_cache: Dict[str, int] = {}
        self._location_cache: Dict[str, int] = {}
        self._user_cache: Dict[str, int] = {}

    def _request(self, method: str, path: str, body: Optional[dict] = None, query: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        if query:
            qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
            url = f"{url}?{qs}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url=url, data=data, method=method, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            payload = e.read().decode("utf-8", errors="replace")
            raise HttpError(e.code, payload) from e

    def _paginate_rows(self, path: str, search: Optional[str] = None) -> List[dict]:
        rows: List[dict] = []
        offset = 0
        limit = 500

        while True:
            data = self._request("GET", path, query={"offset": offset, "limit": limit, "search": search})
            batch = data.get("rows", [])
            rows.extend(batch)
            total = int(data.get("total", len(rows)))
            offset += len(batch)
            if not batch or offset >= total:
                break

        return rows

    def resolve_status_id(self, status_name: str) -> int:
        key = status_name.strip().lower()
        if not key:
            raise ValueError("Status is empty")
        if key in self._status_cache:
            return self._status_cache[key]

        rows = self._paginate_rows("/api/v1/statuslabels", search=status_name)
        for row in rows:
            if row.get("name", "").strip().lower() == key:
                self._status_cache[key] = int(row["id"])
                return self._status_cache[key]

        raise ValueError(f"Cannot find status label: {status_name}")

    def resolve_model_id(self, model_name: str) -> int:
        key = model_name.strip().lower()
        if not key:
            raise ValueError("Model is empty")
        if key in self._model_cache:
            return self._model_cache[key]

        rows = self._paginate_rows("/api/v1/models", search=model_name)
        for row in rows:
            if row.get("name", "").strip().lower() == key:
                self._model_cache[key] = int(row["id"])
                return self._model_cache[key]

        raise ValueError(f"Cannot find model: {model_name}")

    def resolve_location_id(self, location_name: str) -> Optional[int]:
        key = location_name.strip().lower()
        if not key:
            return None
        if key in self._location_cache:
            return self._location_cache[key]

        rows = self._paginate_rows("/api/v1/locations", search=location_name)
        for row in rows:
            if row.get("name", "").strip().lower() == key:
                self._location_cache[key] = int(row["id"])
                return self._location_cache[key]

        return None

    def resolve_user_id(self, username: str, email: str) -> Optional[int]:
        key = (username or email or "").strip().lower()
        if not key:
            return None
        if key in self._user_cache:
            return self._user_cache[key]

        rows = self._paginate_rows("/api/v1/users", search=key)
        for row in rows:
            row_username = str(row.get("username", "")).strip().lower()
            row_email = str(row.get("email", "")).strip().lower()
            if key in (row_username, row_email):
                self._user_cache[key] = int(row["id"])
                return self._user_cache[key]

        return None

    def create_asset(self, row: dict) -> Tuple[int, str]:
        model_name = str(row.get("Model", "")).strip()
        status_name = str(row.get("Status", "")).strip()
        asset_tag = str(row.get("Asset Tag", "")).strip()
        serial = str(row.get("Serial Number", "")).strip()
        purchase_date = str(row.get("Purchase Date", "")).strip()
        purchase_cost = self._normalize_purchase_cost(str(row.get("Purchase Cost", "")).strip())
        notes = str(row.get("Asset Notes", "")).strip()
        name = str(row.get("Name", "")).strip() or asset_tag

        if not model_name or not status_name:
            raise ValueError("Missing required columns: Model/Status")

        payload = {
            "model_id": self.resolve_model_id(model_name),
            "status_id": self.resolve_status_id(status_name),
            "asset_tag": asset_tag if asset_tag else None,
            "serial": serial if serial else None,
            "name": name,
            "purchase_date": purchase_date if purchase_date else None,
            "purchase_cost": purchase_cost if purchase_cost else None,
            "notes": notes if notes else None,
        }

        location_id = self.resolve_location_id(str(row.get("Location", "")))
        if location_id:
            payload["location_id"] = location_id

        payload = {k: v for k, v in payload.items() if v is not None}
        data = self._request("POST", "/api/v1/hardware", body=payload)

        if data.get("status") != "success":
            raise ValueError(f"Create asset failed: {json.dumps(data)}")

        asset_id = int(data["payload"]["id"])
        created_asset_tag = str(data["payload"].get("asset_tag", asset_tag))
        return asset_id, created_asset_tag

    @staticmethod
    def _normalize_purchase_cost(raw_value: str) -> Optional[str]:
        value = raw_value.strip()
        if not value:
            return None

        # Remove currency symbols and spaces, keep only digits and separators.
        filtered = re.sub(r"[^0-9,.-]", "", value)
        if not filtered:
            return None

        # Handle common formats:
        # - 1,234.56 -> 1234.56
        # - 1.234,56 -> 1234.56
        # - 123,45   -> 123.45
        if "," in filtered and "." in filtered:
            if filtered.rfind(",") > filtered.rfind("."):
                filtered = filtered.replace(".", "").replace(",", ".")
            else:
                filtered = filtered.replace(",", "")
        elif "," in filtered:
            parts = filtered.split(",")
            if len(parts[-1]) in (1, 2):
                filtered = "".join(parts[:-1]).replace(".", "") + "." + parts[-1]
            else:
                filtered = filtered.replace(",", "")
        else:
            if filtered.count(".") > 1:
                filtered = filtered.replace(".", "")

        try:
            amount = float(filtered)
        except ValueError:
            return None

        if amount < 0:
            return None

        # Keep compact numeric string; Snipe-IT accepts plain number text.
        if amount.is_integer():
            return str(int(amount))
        return f"{amount:.2f}".rstrip("0").rstrip(".")

    def checkout_asset(self, asset_id: int, row: dict) -> bool:
        checkout_type = str(row.get("Checkout Type", "")).strip().lower()
        if not checkout_type:
            return False

        location_id = self.resolve_location_id(str(row.get("Checkout to Location", "")))
        username = str(row.get("Checked Out To: Username", "")).strip()
        email = str(row.get("Checked Out To: Email", "")).strip()
        assigned_user_id = self.resolve_user_id(username, email)

        payload = {}
        if checkout_type == "location" and location_id:
            payload["checkout_to_type"] = "location"
            payload["assigned_location"] = location_id
        elif checkout_type in ("user", "username") and assigned_user_id:
            payload["checkout_to_type"] = "user"
            payload["assigned_user"] = assigned_user_id
        elif assigned_user_id:
            payload["checkout_to_type"] = "user"
            payload["assigned_user"] = assigned_user_id
        elif location_id:
            payload["checkout_to_type"] = "location"
            payload["assigned_location"] = location_id
        else:
            return False

        data = self._request("POST", f"/api/v1/hardware/{asset_id}/checkout", body=payload)
        return data.get("status") == "success"

    def fetch_asset_status_counts(self) -> Tuple[int, Dict[str, int]]:
        rows = self._paginate_rows("/api/v1/hardware")
        counts: Dict[str, int] = {}

        for row in rows:
            status_obj = row.get("status_label") or {}
            status_name = str(status_obj.get("name", "Unknown")).strip() or "Unknown"
            counts[status_name] = counts.get(status_name, 0) + 1

        total = sum(counts.values())
        return total, counts


def _format_pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "0.0%"
    return f"{(part / whole) * 100:.1f}%"


def build_report_text(
    *,
    title: str,
    total: int,
    status_counts: Dict[str, int],
    deployed_status_names: List[str],
    available_status_names: List[str],
    extra_lines: Optional[List[str]] = None,
) -> str:
    normalized = {k.lower(): v for k, v in status_counts.items()}

    deployed = sum(normalized.get(name.lower(), 0) for name in deployed_status_names)
    available = sum(normalized.get(name.lower(), 0) for name in available_status_names)

    lines = [
        f"*{title}*",
        f"- Total assets: *{total}*",
        f"- Deployed: *{deployed}/{total}* ({_format_pct(deployed, total)})",
        f"- Available: *{available}*",
        "- By status:",
    ]

    for name, value in sorted(status_counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        lines.append(f"  - {name}: {value}")

    if extra_lines:
        lines.append("")
        lines.extend(extra_lines)

    return "\n".join(lines)


def send_google_chat_message(webhook_url: str, text: str) -> None:
    req = urllib.request.Request(
        url=webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )
    with urllib.request.urlopen(req, timeout=20) as _:
        return


def load_status_list_from_env(var_name: str, default_value: List[str]) -> List[str]:
    raw = os.getenv(var_name, "")
    if not raw.strip():
        return default_value
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_runtime_config() -> Dict[str, str]:
    global _RUNTIME_CONFIG_CACHE
    if _RUNTIME_CONFIG_CACHE is not None:
        return _RUNTIME_CONFIG_CACHE

    secret_id = os.getenv("SECRETS_BUNDLE_ID", "").strip()
    if secret_id:
        client = boto3.client("secretsmanager")
        result = client.get_secret_value(SecretId=secret_id)
        raw = result.get("SecretString", "")
        if not raw:
            raise ValueError("Secrets bundle is empty")

        payload = json.loads(raw)
        _RUNTIME_CONFIG_CACHE = {
            "snipeit_base_url": str(payload.get("snipeit_base_url", "")).strip(),
            "snipeit_api_token": str(payload.get("snipeit_api_token", "")).strip(),
            "google_chat_webhook": str(payload.get("google_chat_webhook", "")).strip(),
            "user_default_password": str(payload.get("user_default_password", "")).strip(),
        }
    else:
        # Backward-compatible fallback when secret is not configured.
        _RUNTIME_CONFIG_CACHE = {
            "snipeit_base_url": os.getenv("SNIPEIT_BASE_URL", "").strip(),
            "snipeit_api_token": os.getenv("SNIPEIT_API_TOKEN", "").strip(),
            "google_chat_webhook": os.getenv("GOOGLE_CHAT_WEBHOOK", "").strip(),
            "user_default_password": os.getenv("USER_DEFAULT_PASSWORD", "").strip(),
        }

    if not _RUNTIME_CONFIG_CACHE["snipeit_base_url"] or not _RUNTIME_CONFIG_CACHE["snipeit_api_token"]:
        raise ValueError("Missing required Snipe-IT runtime secrets")

    return _RUNTIME_CONFIG_CACHE
