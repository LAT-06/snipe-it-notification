import base64
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from common import (
    SnipeITClient,
    build_lifecycle_alert_lines,
    build_report_text,
    load_int_from_env,
    load_runtime_config,
    load_status_list_from_env,
    send_google_chat_message,
)


def _response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "username", "email", "full_name", "display_name", "label", "value", "text"):
            name = _as_text(value.get(key))
            if name:
                return name
        return ""

    if isinstance(value, list):
        for item in value:
            name = _extract_name(item)
            if name:
                return name
        return ""

    return _as_text(value)


def _looks_like_asset_tag(value: str) -> bool:
    text = _as_text(value)
    if not text:
        return False

    # Heuristic: tags are compact tokens and usually contain digits.
    if not re.match(r"^[A-Za-z0-9._-]{3,64}$", text):
        return False

    return bool(re.search(r"\d", text))


def _sanitize_event_fragment(value: str, max_len: int = 120) -> str:
    text = _as_text(value)
    if not text:
        return ""

    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = text.replace("<", "(").replace(">", ")").replace("|", "/")
    text = re.sub(r"(?i)(?<![A-Za-z0-9._%+-])@(?:all|here)\b", "(mention)", text)

    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."

    return text


def _sanitize_asset_tag(value: str) -> str:
    candidate = _sanitize_event_fragment(value, max_len=64)
    if _looks_like_asset_tag(candidate):
        return candidate
    return "Unknown asset"


def _strip_link_markup(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"<[^|>]+\|([^>]+)>", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", cleaned)
    return cleaned.strip()


def _collect_text_fragments(value: Any, out: List[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_text_fragments(item, out)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_fragments(item, out)
        return

    text = _as_text(value)
    if text:
        out.append(text)


def _extract_asset_tag_from_text(text: str) -> str:
    if not text:
        return ""

    # Slack-style link text: <url|DX0086>
    linked = re.search(r"<[^|>]+\|([^>]+)>", text)
    if linked:
        candidate = linked.group(1).strip()
        if _looks_like_asset_tag(candidate):
            return candidate

    explicit = re.search(r"(?i)asset\s*tag\s*[:=-]\s*([A-Za-z0-9._-]+)", text)
    if explicit:
        candidate = explicit.group(1).strip()
        if _looks_like_asset_tag(candidate):
            return candidate

    # Common asset tag patterns (DX0086, LAPTOP1234, etc.)
    generic = re.search(r"\b[A-Z]{1,10}[0-9]{2,}\b", text)
    if generic:
        candidate = generic.group(0).strip()
        if _looks_like_asset_tag(candidate):
            return candidate

    return ""


def _extract_status_transition_from_text(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""

    def looks_like_status(value: str) -> bool:
        lowered = value.lower().strip()
        status_keywords = [
            "deployed",
            "in hold",
            "hold",
            "ready",
            "available",
            "in use",
            "pending",
            "retired",
            "broken",
            "repair",
            "lost",
            "status",
        ]
        return any(keyword in lowered for keyword in status_keywords)

    arrow = re.search(r"(?i)([A-Za-z][A-Za-z\s-]+?)\s*->\s*([A-Za-z][A-Za-z\s-]+)", text)
    if arrow:
        left = arrow.group(1).strip()
        right = arrow.group(2).strip()
        if left and right and ("status" in text.lower() or (looks_like_status(left) and looks_like_status(right))):
            return left, right

    frm_to = re.search(r"(?i)(?:status\s*)?(?:changed\s*)?from\s+([A-Za-z][A-Za-z\s-]+?)\s+to\s+([A-Za-z][A-Za-z\s-]+)", text)
    if frm_to:
        left = frm_to.group(1).strip()
        right = frm_to.group(2).strip()
        if left and right and ("status" in text.lower() or (looks_like_status(left) and looks_like_status(right))):
            return left, right

    return "", ""


def _extract_assignee_transition_from_text(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""

    arrow = re.search(r"(?i)\(([^)]+)\)\s*->\s*assign\s+to\s+([^\n|]+)", text)
    if arrow:
        return arrow.group(1).strip(), arrow.group(2).strip()

    frm_to = re.search(r"(?i)assigned\s*(?:user|to)?\s*from\s+([^\n|]+?)\s+to\s+([^\n|]+)", text)
    if frm_to:
        return frm_to.group(1).strip(), frm_to.group(2).strip()

    assign_to = re.search(r"(?i)assign(?:ed)?\s+to\s+([^\n|]+)", text)
    if assign_to:
        return "unassigned", assign_to.group(1).strip()

    return "", ""


def _extract_assignee_from_text(text: str) -> str:
    if not text:
        return ""

    candidate_patterns = [
        r"(?i)checked\s*out\s*to\s+([^\n|]+)",
        r"(?i)assigned\s*to\s+([^\n|]+)",
        r"(?i)assign\s*to\s+([^\n|]+)",
        r"(?i)user\s*[:=-]\s*([^\n|]+)",
        r"(?i)to\s*[:=-]\s*([^\n|]+)",
    ]

    for pattern in candidate_patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        candidate = _strip_link_markup(match.group(1)).strip(" .,-")
        if candidate and not _looks_like_asset_tag(candidate):
            return candidate

    return ""


def _extract_hardware_id_from_text(text: str) -> Optional[int]:
    if not text:
        return None

    url_match = re.search(r"/hardware/(\d+)", text)
    if url_match:
        return int(url_match.group(1))

    key_match = re.search(r"(?i)(?:asset_id|hardware_id)\s*[:=-]\s*(\d+)", text)
    if key_match:
        return int(key_match.group(1))

    return None


def _extract_hardware_id(payload: dict) -> Optional[int]:
    direct = _first_value_by_keys(payload, ["asset_id", "hardware_id"])
    if direct is not None:
        try:
            value = int(str(direct).strip())
            if value > 0:
                return value
        except ValueError:
            pass

    fragments: List[str] = []
    _collect_text_fragments(payload, fragments)
    for fragment in fragments:
        extracted = _extract_hardware_id_from_text(fragment)
        if extracted is not None:
            return extracted

    return None


def _extract_attachment_context(payload: dict) -> Dict[str, str]:
    context = {"asset_tag": "", "assignee": ""}
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        return context

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue

        text_candidates = [
            _as_text(attachment.get("title")),
            _as_text(attachment.get("text")),
            _as_text(attachment.get("fallback")),
            _as_text(attachment.get("pretext")),
            _as_text(attachment.get("title_link")),
        ]

        for text in text_candidates:
            if text and not context["asset_tag"]:
                tag = _extract_asset_tag_from_text(_strip_link_markup(text))
                if tag:
                    context["asset_tag"] = tag

            if text and not context["assignee"]:
                assignee = _extract_assignee_from_text(_strip_link_markup(text))
                if assignee:
                    context["assignee"] = assignee

        fields = attachment.get("fields")
        if not isinstance(fields, list):
            continue

        for field in fields:
            if not isinstance(field, dict):
                continue

            title = _as_text(field.get("title")).lower()
            value = _strip_link_markup(_as_text(field.get("value")))

            if value and not context["asset_tag"] and ("asset" in title or "tag" in title):
                tag = _extract_asset_tag_from_text(value)
                if tag:
                    context["asset_tag"] = tag

            if value and not context["assignee"] and (
                "assigned" in title
                or "checked out to" in title
                or title == "to"
                or "user" in title
            ):
                if not _looks_like_asset_tag(value):
                    context["assignee"] = value.strip()

    return context


def _infer_event_name_from_text(text: str) -> str:
    lowered = text.lower()
    if "delete" in lowered or "deleted" in lowered:
        return "deleted"
    if "check in" in lowered or "checked in" in lowered:
        return "checked in"
    if "check out" in lowered or "checked out" in lowered:
        return "checked out"
    if "assign" in lowered:
        return "assigned"
    if "status" in lowered or "in hold" in lowered or "deployed" in lowered:
        return "status changed"
    return ""


def _event_name_has_phrase(event_name: str, phrase: str) -> bool:
    if not event_name or not phrase:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, event_name.lower()) is not None


def _first_value_by_keys(obj: Any, keys: List[str]) -> Any:
    key_set = {k.lower() for k in keys}

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            lowered = {str(k).lower(): v for k, v in value.items()}
            for key in key_set:
                if key in lowered:
                    candidate = lowered[key]
                    if isinstance(candidate, (dict, list)):
                        return candidate
                    if _as_text(candidate):
                        return candidate
            for nested in value.values():
                found = walk(nested)
                if found is not None:
                    return found

        if isinstance(value, list):
            for nested in value:
                found = walk(nested)
                if found is not None:
                    return found

        return None

    return walk(obj)


def _parse_transition(value: Any) -> Tuple[str, str]:
    if isinstance(value, dict):
        old_value = _extract_name(
            value.get("from")
            or value.get("old")
            or value.get("before")
            or value.get("previous")
            or value.get("prior")
        )
        new_value = _extract_name(
            value.get("to")
            or value.get("new")
            or value.get("after")
            or value.get("current")
            or value.get("updated")
        )
        if old_value or new_value:
            return old_value, new_value

        old_value = _extract_name(_first_value_by_keys(value, ["old", "from", "before", "previous"]))
        new_value = _extract_name(_first_value_by_keys(value, ["new", "to", "after", "current"]))
        return old_value, new_value

    if isinstance(value, list) and len(value) >= 2:
        return _extract_name(value[0]), _extract_name(value[1])

    text = _as_text(value)
    if "->" in text:
        left, right = text.split("->", 1)
        return left.strip(), right.strip()

    return "", ""


def _extract_transition(
    payload: dict,
    keys: List[str],
    old_fallback_keys: Optional[List[str]] = None,
    new_fallback_keys: Optional[List[str]] = None,
) -> Tuple[str, str]:
    containers: List[Any] = [payload]

    for container_key in ("changes", "change", "diff", "payload", "data", "event"):
        candidate = _first_value_by_keys(payload, [container_key])
        if isinstance(candidate, (dict, list)):
            containers.append(candidate)

    for container in containers:
        if not isinstance(container, dict):
            continue
        lowered = {str(k).lower(): v for k, v in container.items()}
        for key in keys:
            if key.lower() in lowered:
                old_value, new_value = _parse_transition(lowered[key.lower()])
                if old_value or new_value:
                    return old_value, new_value

    old_keys = [f"old_{key}" for key in keys]
    new_keys = [f"new_{key}" for key in keys]
    if old_fallback_keys:
        old_keys.extend(old_fallback_keys)
    if new_fallback_keys:
        new_keys.extend(new_fallback_keys)

    old_value = _extract_name(_first_value_by_keys(payload, old_keys))
    new_value = _extract_name(_first_value_by_keys(payload, new_keys))
    return old_value, new_value


def _extract_asset_tag(payload: dict) -> str:
    tag = _extract_name(_first_value_by_keys(payload, ["asset_tag", "tag"]))
    if tag and _looks_like_asset_tag(tag):
        return tag

    asset_obj = _first_value_by_keys(payload, ["asset", "item", "hardware"])
    if isinstance(asset_obj, dict):
        tag = _extract_name(asset_obj.get("asset_tag") or asset_obj.get("tag") or asset_obj.get("name"))
        if tag and _looks_like_asset_tag(tag):
            return tag

    fragments: List[str] = []
    _collect_text_fragments(payload, fragments)
    for fragment in fragments:
        tag = _extract_asset_tag_from_text(fragment)
        if tag:
            return tag

    return "Unknown asset"


def _extract_current_assignee(payload: dict) -> str:
    for key in ("assigned_to", "assigned_user", "checkout_to", "user", "owner", "assignee"):
        value = _first_value_by_keys(payload, [key])
        if value is not None:
            name = _extract_name(value)
            if name:
                return name
    return "unassigned"


def _extract_event_name(payload: dict) -> str:
    raw = _extract_name(_first_value_by_keys(payload, ["event", "action", "event_type", "type", "name", "verb"]))
    if raw:
        return raw.lower().replace("_", " ")

    fragments: List[str] = []
    _collect_text_fragments(payload, fragments)
    combined = " | ".join(fragments)
    return _infer_event_name_from_text(combined)


def _build_event_lines(payload: dict, asset_context: Optional[Dict[str, str]] = None) -> List[str]:
    asset_tag = _extract_asset_tag(payload)
    event_name = _extract_event_name(payload)
    asset_context = asset_context or {}
    attachment_context = _extract_attachment_context(payload)

    fragments: List[str] = []
    _collect_text_fragments(payload, fragments)
    combined_text = " | ".join(fragments)

    old_status, new_status = _extract_transition(
        payload,
        ["status", "status_label", "statuslabel"],
        old_fallback_keys=["from_status", "old_status", "previous_status"],
        new_fallback_keys=["to_status", "new_status", "current_status"],
    )
    old_assignee, new_assignee = _extract_transition(
        payload,
        ["assigned_to", "assigned_user", "assignee", "checkout_to"],
        old_fallback_keys=["from_assignee", "old_assignee", "previous_assignee"],
        new_fallback_keys=["to_assignee", "new_assignee", "current_assignee"],
    )

    if not (old_status or new_status):
        old_status, new_status = _extract_status_transition_from_text(combined_text)

    if not (old_assignee or new_assignee):
        old_assignee, new_assignee = _extract_assignee_transition_from_text(combined_text)

    if asset_tag == "Unknown asset":
        fallback_tag = _extract_asset_tag_from_text(combined_text)
        if fallback_tag:
            asset_tag = fallback_tag

    attachment_tag = _as_text(attachment_context.get("asset_tag"))
    if attachment_tag and (asset_tag == "Unknown asset" or not _looks_like_asset_tag(asset_tag)):
        asset_tag = attachment_tag

    context_tag = _as_text(asset_context.get("asset_tag"))
    if context_tag and (_looks_like_asset_tag(context_tag)):
        if asset_tag == "Unknown asset" or not _looks_like_asset_tag(asset_tag):
            asset_tag = context_tag

    current_assignee = _extract_current_assignee(payload)
    if current_assignee == "unassigned":
        assignee_from_text = _extract_name(_first_value_by_keys(payload, ["assigned", "assignee", "user", "target"]))
        if assignee_from_text:
            current_assignee = assignee_from_text

    attachment_assignee = _as_text(attachment_context.get("assignee"))
    if attachment_assignee and current_assignee == "unassigned":
        current_assignee = attachment_assignee

    context_assignee = _as_text(asset_context.get("assignee"))
    if context_assignee:
        current_assignee = context_assignee

    current_status = _as_text(asset_context.get("status"))
    if not current_status and new_status:
        current_status = new_status

    asset_tag = _sanitize_asset_tag(asset_tag)
    old_status = _sanitize_event_fragment(old_status, max_len=40)
    new_status = _sanitize_event_fragment(new_status, max_len=40)
    old_assignee = _sanitize_event_fragment(old_assignee, max_len=80)
    new_assignee = _sanitize_event_fragment(new_assignee, max_len=80)
    current_assignee = _sanitize_event_fragment(current_assignee, max_len=80) or "unassigned"
    current_status = _sanitize_event_fragment(current_status, max_len=40)
    event_name = _sanitize_event_fragment(event_name, max_len=60).lower()

    lines: List[str] = []

    if old_status and new_status and old_status.lower() != new_status.lower():
        target = new_assignee or current_assignee or "unassigned"
        lines.append(f"{asset_tag} {old_status.lower()} -> {new_status.lower()} ({target})")

    if (old_assignee or new_assignee) and old_assignee != new_assignee:
        source = old_assignee or "unassigned"
        if new_assignee:
            lines.append(f"{asset_tag} ({source}) -> assign to {new_assignee}")
        else:
            lines.append(f"{asset_tag} ({source}) -> unassigned")

    if not lines:
        status_suffix = f" (status: {current_status})" if current_status else ""
        if _event_name_has_phrase(event_name, "delete") or _event_name_has_phrase(event_name, "deleted"):
            lines.append(f"{asset_tag} deleted")
        elif _event_name_has_phrase(event_name, "check in") or _event_name_has_phrase(event_name, "checked in"):
            lines.append(f"{asset_tag} checked in{status_suffix}")
        elif _event_name_has_phrase(event_name, "check out") or _event_name_has_phrase(event_name, "checked out"):
            lines.append(f"{asset_tag} checked out to {current_assignee}{status_suffix}")
        elif event_name:
            lines.append(f"{asset_tag} event: {event_name}")
        else:
            lines.append(f"{asset_tag} updated")

    # Keep order, remove duplicates.
    deduped: List[str] = []
    seen = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)

    return deduped


def _build_snapshot_summary(client: SnipeITClient) -> str:
    deployed_statuses = load_status_list_from_env("DEPLOYED_STATUS_NAMES", ["Deployed", "In Use"])
    available_statuses = load_status_list_from_env("AVAILABLE_STATUS_NAMES", ["Ready", "Available"])
    replacement_age_years = load_int_from_env("ASSET_REPLACEMENT_AGE_YEARS", 3, min_value=1)
    warranty_expiry_lookahead_days = load_int_from_env("WARRANTY_EXPIRY_LOOKAHEAD_DAYS", 30, min_value=1)

    total, status_counts, asset_tags_by_status = client.fetch_asset_status_details()
    warranty_due, warranty_expired, replacement_due = client.fetch_asset_lifecycle_alerts(
        deployed_status_names=deployed_statuses,
        replacement_age_years=replacement_age_years,
        warranty_expiry_lookahead_days=warranty_expiry_lookahead_days,
    )

    extra_lines = build_lifecycle_alert_lines(
        warranty_due=warranty_due,
        warranty_expired=warranty_expired,
        replacement_due=replacement_due,
        replacement_age_years=replacement_age_years,
        warranty_expiry_lookahead_days=warranty_expiry_lookahead_days,
        max_items_per_section=20,
    )

    return build_report_text(
        title="Snipe-IT Import Summary",
        total=total,
        status_counts=status_counts,
        deployed_status_names=deployed_statuses,
        available_status_names=available_statuses,
        detailed_asset_tags_by_status=asset_tags_by_status,
        status_detail_exclude_names=deployed_statuses,
        max_asset_tags_per_status=20,
        extra_lines=extra_lines,
    )


def _extract_payload(event: dict) -> dict:
    body = event.get("body") if isinstance(event, dict) else event
    if body is None:
        return {}

    if isinstance(body, dict):
        return body

    if isinstance(body, str):
        raw = body
        if event.get("isBase64Encoded"):
            try:
                raw = base64.b64decode(raw).decode("utf-8")
            except Exception:
                pass

        if not raw.strip():
            return {}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw_body": raw}

    return {}


def lambda_handler(event, _context):
    try:
        payload = _extract_payload(event if isinstance(event, dict) else {})
        print(
            json.dumps(
                {
                    "event_payload_keys": sorted(list(payload.keys())),
                    "text_preview": _as_text(payload.get("text"))[:500],
                    "attachments_count": len(payload.get("attachments", [])) if isinstance(payload.get("attachments"), list) else 0,
                    "attachment_preview": json.dumps(payload.get("attachments", [{}])[0])[:500]
                    if isinstance(payload.get("attachments"), list) and payload.get("attachments")
                    else "",
                }
            )
        )

        config = load_runtime_config()
        chat_webhook = config["google_chat_webhook"]

        client = SnipeITClient(config["snipeit_base_url"], config["snipeit_api_token"])

        hardware_id = _extract_hardware_id(payload)
        asset_context: Dict[str, str] = {}
        if hardware_id is not None:
            asset_context = client.fetch_asset_event_context(hardware_id)
            print(json.dumps({"hardware_id": hardware_id, "asset_context": asset_context}))

        lines = _build_event_lines(payload, asset_context=asset_context)

        snapshot_summary = _build_snapshot_summary(client)

        event_block = "\n".join(["*Snipe-IT Webhook Event*"] + [f"- {line}" for line in lines])
        final_text = f"{event_block}\n\n{snapshot_summary}"
        send_google_chat_message(chat_webhook, final_text)

        return _response(200, {"ok": True, "event_lines": lines})
    except Exception as exc:
        print(f"asset_event_handler error: {exc}")
        return _response(500, {"ok": False, "error": str(exc)})
