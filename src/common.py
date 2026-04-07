import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
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
        warranty_months = self._normalize_warranty_months(str(row.get("Warranty", "")).strip())
        eol_date = self._normalize_date_for_payload(str(row.get("EOL Date", "")).strip())
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
            "warranty_months": warranty_months,
            "eol": eol_date,
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
    def _normalize_warranty_months(raw_value: str) -> Optional[int]:
        value = raw_value.strip().lower()
        if not value:
            return None

        digits = re.sub(r"[^0-9]", "", value)
        if digits:
            months = int(digits)
            return months if months > 0 else None

        return None

    @staticmethod
    def _normalize_date_for_payload(raw_value: str) -> Optional[str]:
        value = raw_value.strip()
        if not value:
            return None

        parsed = SnipeITClient._extract_date(value)
        if parsed is None:
            return None

        return parsed.isoformat()

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
        total, counts, _ = self.fetch_asset_status_details()
        return total, counts

    def fetch_asset_status_details(self) -> Tuple[int, Dict[str, int], Dict[str, List[str]]]:
        rows = self._paginate_rows("/api/v1/hardware")
        counts: Dict[str, int] = {}
        asset_tags_by_status: Dict[str, List[str]] = {}

        for row in rows:
            status_obj = row.get("status_label") or {}
            status_name = str(status_obj.get("name", "Unknown")).strip() or "Unknown"
            counts[status_name] = counts.get(status_name, 0) + 1

            asset_tag = str(row.get("asset_tag", "")).strip()
            if asset_tag:
                asset_tags_by_status.setdefault(status_name, []).append(asset_tag)

        total = sum(counts.values())

        # Keep deterministic ordering for message output.
        for status_name in asset_tags_by_status:
            asset_tags_by_status[status_name].sort()

        return total, counts, asset_tags_by_status

    @staticmethod
    def _extract_date(value: object) -> Optional[date]:
        if value is None:
            return None

        if isinstance(value, dict):
            for key in ("date", "datetime", "value", "formatted"):
                parsed = SnipeITClient._extract_date(value.get(key))
                if parsed is not None:
                    return parsed
            return None

        raw = str(value).strip()
        if not raw:
            return None

        # Normalize common ISO format variants.
        if "T" in raw:
            raw = raw.split("T", 1)[0]

        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass

        match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                return None

        return None

    @staticmethod
    def _extract_assignee_text(row: dict) -> str:
        assigned_to = row.get("assigned_to")
        if isinstance(assigned_to, dict):
            for key in ("name", "username", "email"):
                value = str(assigned_to.get(key, "")).strip()
                if value:
                    return value
            return ""

        if assigned_to is not None:
            value = str(assigned_to).strip()
            if value:
                return value

        checkout_to = row.get("checkout_to")
        if isinstance(checkout_to, dict):
            for key in ("name", "username", "email"):
                value = str(checkout_to.get(key, "")).strip()
                if value:
                    return value

        return ""

    @staticmethod
    def _extract_int(value: object) -> Optional[int]:
        if value is None:
            return None

        if isinstance(value, dict):
            for key in ("value", "raw", "formatted"):
                extracted = SnipeITClient._extract_int(value.get(key))
                if extracted is not None:
                    return extracted
            return None

        raw = str(value).strip()
        if not raw:
            return None

        digits = re.sub(r"[^0-9]", "", raw)
        if not digits:
            return None

        result = int(digits)
        return result if result > 0 else None

    @staticmethod
    def _add_months(start_date: date, months: int) -> date:
        year = start_date.year + (start_date.month - 1 + months) // 12
        month = (start_date.month - 1 + months) % 12 + 1
        month_lengths = [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ]
        day = min(start_date.day, month_lengths[month - 1])
        return date(year, month, day)

    def fetch_asset_lifecycle_alerts(
        self,
        *,
        deployed_status_names: List[str],
        replacement_age_years: int,
        warranty_expiry_lookahead_days: int,
        today: Optional[date] = None,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
        rows = self._paginate_rows("/api/v1/hardware")
        today = today or datetime.utcnow().date()

        deployed_set = {name.strip().lower() for name in deployed_status_names if name.strip()}
        warranty_due: List[Dict[str, str]] = []
        warranty_expired: List[Dict[str, str]] = []
        replacement_due: List[Dict[str, str]] = []

        for row in rows:
            status_obj = row.get("status_label") or {}
            status_name = str(status_obj.get("name", "Unknown")).strip() or "Unknown"
            status_l = status_name.lower()

            asset_tag = str(row.get("asset_tag", "")).strip() or f"ID-{row.get('id', 'N/A')}"
            assignee = self._extract_assignee_text(row)

            warranty_date = self._extract_date(row.get("warranty_expires"))
            if warranty_date is None:
                purchase_date_for_warranty = self._extract_date(row.get("purchase_date"))
                warranty_months = self._extract_int(row.get("warranty_months"))
                if purchase_date_for_warranty is not None and warranty_months is not None:
                    warranty_date = self._add_months(purchase_date_for_warranty, warranty_months)

            if warranty_date is not None:
                days_left = (warranty_date - today).days
                if 0 <= days_left <= warranty_expiry_lookahead_days:
                    warranty_due.append(
                        {
                            "asset_tag": asset_tag,
                            "status": status_name,
                            "warranty_date": warranty_date.isoformat(),
                            "days_left": str(days_left),
                            "assignee": assignee,
                        }
                    )
                elif days_left < 0:
                    warranty_expired.append(
                        {
                            "asset_tag": asset_tag,
                            "status": status_name,
                            "warranty_date": warranty_date.isoformat(),
                            "days_overdue": str(abs(days_left)),
                            "assignee": assignee,
                        }
                    )

            purchase_date = self._extract_date(row.get("purchase_date"))
            if purchase_date is None:
                continue

            age_years = (today - purchase_date).days / 365.25
            if age_years >= float(replacement_age_years) and status_l in deployed_set:
                replacement_due.append(
                    {
                        "asset_tag": asset_tag,
                        "status": status_name,
                        "purchase_date": purchase_date.isoformat(),
                        "age_years": f"{age_years:.1f}",
                        "assignee": assignee,
                    }
                )

        warranty_due.sort(key=lambda item: (int(item["days_left"]), item["asset_tag"]))
        warranty_expired.sort(key=lambda item: (-int(item["days_overdue"]), item["asset_tag"]))
        replacement_due.sort(key=lambda item: (-float(item["age_years"]), item["asset_tag"]))
        return warranty_due, warranty_expired, replacement_due


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
    detailed_asset_tags_by_status: Optional[Dict[str, List[str]]] = None,
    status_detail_exclude_names: Optional[List[str]] = None,
    max_asset_tags_per_status: int = 20,
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

    if detailed_asset_tags_by_status:
        excluded = {
            name.strip().lower()
            for name in (status_detail_exclude_names or [])
            if name and name.strip()
        }
        if excluded:
            lines.append("")
            lines.append("- Detailed assets by status:")

            for status_name, count in sorted(status_counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
                if status_name.strip().lower() in excluded:
                    continue

                tags = detailed_asset_tags_by_status.get(status_name, [])
                if not tags:
                    continue

                lines.append(f"  - {status_name}: {count}")
                shown = tags[:max_asset_tags_per_status]
                for asset_tag in shown:
                    lines.append(f"    - {asset_tag}")

                remaining = len(tags) - len(shown)
                if remaining > 0:
                    lines.append(f"    - ... and {remaining} more")

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


def load_int_from_env(var_name: str, default_value: int, min_value: int = 0) -> int:
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return default_value

    try:
        value = int(raw)
    except ValueError:
        return default_value

    return max(min_value, value)


def build_lifecycle_alert_lines(
    *,
    warranty_due: List[Dict[str, str]],
    warranty_expired: List[Dict[str, str]],
    replacement_due: List[Dict[str, str]],
    replacement_age_years: int,
    warranty_expiry_lookahead_days: int,
    max_items_per_section: int = 20,
) -> List[str]:
    lines: List[str] = []

    lines.append(f"Warranty expiring in next {warranty_expiry_lookahead_days} days: {len(warranty_due)}")
    if warranty_due:
        for item in warranty_due[:max_items_per_section]:
            suffix = f" | User: {item['assignee']}" if item.get("assignee") else ""
            lines.append(
                f"- {item['asset_tag']} | Warranty: {item['warranty_date']} | In {item['days_left']} days | Status: {item['status']}{suffix}"
            )
        remaining = len(warranty_due) - min(len(warranty_due), max_items_per_section)
        if remaining > 0:
            lines.append(f"- ... and {remaining} more")

    lines.append("")
    lines.append(f"Warranty expired: {len(warranty_expired)}")
    if warranty_expired:
        for item in warranty_expired[:max_items_per_section]:
            suffix = f" | User: {item['assignee']}" if item.get("assignee") else ""
            lines.append(
                f"- {item['asset_tag']} | Expired: {item['warranty_date']} | Overdue {item['days_overdue']} days | Status: {item['status']}{suffix}"
            )
        remaining = len(warranty_expired) - min(len(warranty_expired), max_items_per_section)
        if remaining > 0:
            lines.append(f"- ... and {remaining} more")

    lines.append("")
    lines.append(
        f"Replacement candidates (>= {replacement_age_years} years, currently deployed): {len(replacement_due)}"
    )
    if replacement_due:
        for item in replacement_due[:max_items_per_section]:
            assignee = item.get("assignee") or "Unassigned"
            lines.append(
                f"- {item['asset_tag']} | {item['age_years']} years | User: {assignee} | Purchased: {item['purchase_date']}"
            )
        remaining = len(replacement_due) - min(len(replacement_due), max_items_per_section)
        if remaining > 0:
            lines.append(f"- ... and {remaining} more")

    return lines


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
