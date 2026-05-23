from __future__ import annotations

from datetime import datetime, timezone


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
        ts = activity.get("timestamp")
        if ts and (latest_time is None or ts > latest_time):
            latest_time = ts
            latest_type = next(iter(activity.keys()), "")
    if not latest_time:
        return {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}

    parsed = datetime.fromisoformat(latest_time.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - parsed).days
    if age_days <= 30:
        level = "Active"
    elif age_days <= 90:
        level = "Recently Modified"
    elif age_days <= 365:
        level = "Stale"
    else:
        level = "Dormant"
    return {"activity_level": level, "last_activity_time": latest_time, "last_activity_type": latest_type}

