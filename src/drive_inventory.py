from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .classifier import classify_file
from .drive_activity import enrich_activity


@dataclass
class InventoryRow:
    file_id: str
    name: str
    mime_type: str
    parents: str
    created_time: str
    modified_time: str
    owners: str
    size: str
    web_view_link: str
    suggested_role: str
    suggested_sensitivity: str
    suggested_destination: str
    activity_level: str
    last_activity_time: str
    last_activity_type: str
    review_decision: str = ""
    final_destination: str = ""
    notes: str = ""


def _safe_join(items) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        return "; ".join(str(i) for i in items)
    return str(items)


def inventory_files(drive_service, activity_service=None, include_folders: bool = False, activity_enrichment: bool = False):
    rows = []
    page_token = None
    query = "trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, parents, createdTime, modifiedTime, owners(displayName, emailAddress), webViewLink, size)"
    while True:
        response = drive_service.files().list(q=query, spaces="drive", pageSize=1000, fields=fields, pageToken=page_token, orderBy="modifiedTime desc").execute()
        for file in response.get("files", []):
            if file["mimeType"] == "application/vnd.google-apps.folder" and not include_folders:
                continue
            role, sensitivity, destination = classify_file(file.get("name", ""), file.get("mimeType", ""))
            activity = {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}
            if activity_enrichment and activity_service:
                activity = enrich_activity(activity_service, file["id"])
            rows.append(
                InventoryRow(
                    file_id=file.get("id", ""),
                    name=file.get("name", ""),
                    mime_type=file.get("mimeType", ""),
                    parents=_safe_join(file.get("parents", [])),
                    created_time=file.get("createdTime", ""),
                    modified_time=file.get("modifiedTime", ""),
                    owners=_safe_join([o.get("displayName") or o.get("emailAddress") for o in file.get("owners", [])]),
                    size=str(file.get("size", "")),
                    web_view_link=file.get("webViewLink", ""),
                    suggested_role=role,
                    suggested_sensitivity=sensitivity,
                    suggested_destination=destination,
                    activity_level=activity["activity_level"],
                    last_activity_time=activity["last_activity_time"],
                    last_activity_type=activity["last_activity_type"],
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return rows

