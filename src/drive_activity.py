from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def _decode_timestamp_value(timestamp_value) -> str:
    if isinstance(timestamp_value, str):
        return timestamp_value
    if isinstance(timestamp_value, dict):
        seconds = timestamp_value.get("seconds")
        nanos = int(timestamp_value.get("nanos", 0) or 0)
        if seconds is not None:
            dt = datetime.fromtimestamp(int(seconds), tz=timezone.utc)
            if nanos:
                dt = dt.replace(microsecond=nanos // 1000)
            return dt.isoformat().replace("+00:00", "Z")
    return ""


def _extract_timestamp(activity: dict) -> str:
    timestamp = activity.get("timestamp")
    decoded = _decode_timestamp_value(timestamp)
    if decoded:
        return decoded
    time_range = activity.get("timeRange") or {}
    if isinstance(time_range, dict):
        for bound in ("endTime", "startTime"):
            decoded = _decode_timestamp_value(time_range.get(bound))
            if decoded:
                return decoded
    for action in activity.get("actions", []) or []:
        action_time = _decode_timestamp_value(action.get("timestamp"))
        if action_time:
            return action_time
    return ""


def _extract_activity_type(activity: dict) -> str:
    detail = activity.get("primaryActionDetail") or {}
    if isinstance(detail, dict) and detail:
        return next(iter(detail.keys()))
    for action in activity.get("actions", []) or []:
        action_detail = action.get("detail") or {}
        if isinstance(action_detail, dict) and action_detail:
            return next(iter(action_detail.keys()))
    return ""


def _parse_drive_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None


def _classify_age(age_days: int) -> str:
    if age_days <= 30:
        return "Active"
    if age_days <= 90:
        return "Recently Modified"
    if age_days <= 365:
        return "Stale"
    return "Dormant"


def enrich_activity(service, file_id: str) -> dict[str, str]:
    try:
        request = {
            "itemName": f"items/{file_id}",
            "pageSize": 10,
            "consolidationStrategy": {"none": {}},
        }
        response = service.activity().query(body=request).execute()
    except Exception:
        return {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}

    activities = response.get("activities", []) or []
    if not activities:
        return {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}

    latest_time = None
    latest_type = ""
    for activity in activities:
        ts = _extract_timestamp(activity)
        if ts and (latest_time is None or ts > latest_time):
            latest_time = ts
            latest_type = _extract_activity_type(activity)
    if not latest_time:
        return {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}

    parsed = _parse_drive_time(latest_time)
    if parsed is None:
        return {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days
    return {
        "activity_level": _classify_age(age_days),
        "last_activity_time": latest_time,
        "last_activity_type": latest_type or "unknown",
    }
