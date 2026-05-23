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
    current_path: str
    owned_by_me: str
    capabilities_can_move_item_within_drive: str
    capabilities_can_move_item_out_of_drive: str
    capabilities_can_add_my_drive_parent: str
    capabilities_can_remove_my_drive_parent: str
    is_shortcut: str
    shortcut_target_id: str
    shortcut_target_mime_type: str
    shortcut_target_resource_key: str
    suggested_role: str
    suggested_sensitivity: str
    suggested_destination: str
    suggested_confidence: str
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


def _build_folder_cache(drive_service) -> dict[str, dict[str, str]]:
    cache: dict[str, dict[str, str]] = {}
    page_token = None
    fields = "nextPageToken, files(id, name, parents, mimeType, shortcutDetails)"
    while True:
        try:
            response = drive_service.files().list(
                q="trashed = false and mimeType = 'application/vnd.google-apps.folder'",
                spaces="drive",
                pageSize=1000,
                fields=fields,
                pageToken=page_token,
            ).execute()
        except Exception:
            return cache
        for folder in response.get("files", []):
            cache[folder["id"]] = {
                "name": folder.get("name", ""),
                "parent": (folder.get("parents") or [None])[0],
                "mimeType": folder.get("mimeType", ""),
                "shortcutDetails": folder.get("shortcutDetails", {}),
            }
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return cache


def _fetch_folder_metadata(drive_service, folder_cache: dict[str, dict[str, str]], folder_id: str) -> dict[str, str] | None:
    if folder_id in folder_cache:
        return folder_cache[folder_id]
    try:
        response = drive_service.files().get(
            fileId=folder_id,
            fields="id, name, parents, mimeType, shortcutDetails",
        ).execute()
    except Exception:
        return None
    if response.get("mimeType") != "application/vnd.google-apps.folder":
        return None
    parent = (response.get("parents") or [None])[0]
    folder_cache[folder_id] = {
        "name": response.get("name", ""),
        "parent": parent,
        "mimeType": response.get("mimeType", ""),
        "shortcutDetails": response.get("shortcutDetails", {}),
    }
    return folder_cache[folder_id]


def _resolve_shortcut_details(file_metadata: dict) -> tuple[str, str, str]:
    shortcut_details = file_metadata.get("shortcutDetails") or {}
    return (
        str(shortcut_details.get("targetId", "")),
        str(shortcut_details.get("targetMimeType", "")),
        str(shortcut_details.get("targetResourceKey", "")),
    )


def _resolve_path(file_metadata: dict, folder_cache: dict[str, dict[str, str]], drive_service=None) -> tuple[str, str]:
    name = file_metadata.get("name", "")
    parents = file_metadata.get("parents") or []
    if not parents:
        return f"Unknown Parent/{name}", "no parents"
    if len(parents) > 1:
        parent_id = parents[0]
        base = "multiple parents"
    else:
        parent_id = parents[0]
        base = ""
    if not parent_id:
        return f"Unknown Parent/{name}", "missing parent id"

    folder_names: list[str] = []
    visited = set()
    while parent_id and parent_id not in visited:
        visited.add(parent_id)
        folder = folder_cache.get(parent_id)
        if not folder and drive_service is not None:
            folder = _fetch_folder_metadata(drive_service, folder_cache, parent_id)
        if not folder:
            return f"Unknown Parent/{name}", base or "unresolved parent"
        folder_name = folder.get("name") or "Unknown Parent"
        folder_names.append(folder_name)
        parent_id = folder.get("parent")
        if parent_id == "root":
            break
    if not folder_names:
        return f"Unknown Parent/{name}", base or "unresolved parent"
    path = "/".join(["My Drive", *reversed(folder_names), name])
    while "My Drive/My Drive/" in path:
        path = path.replace("My Drive/My Drive/", "My Drive/")
    return path, base


def inventory_files(drive_service, activity_service=None, include_folders: bool = False, activity_enrichment: bool = False, media_policy: str = "role_first"):
    rows = []
    page_token = None
    query = "trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, parents, createdTime, modifiedTime, owners(displayName, emailAddress), webViewLink, size, ownedByMe, capabilities(canMoveItemWithinDrive, canMoveItemOutOfDrive, canAddMyDriveParent, canRemoveMyDriveParent), shortcutDetails)"
    folder_cache = _build_folder_cache(drive_service)
    while True:
        try:
            response = drive_service.files().list(q=query, spaces="drive", pageSize=1000, fields=fields, pageToken=page_token, orderBy="modifiedTime desc").execute()
        except Exception:
            break
        for file in response.get("files", []):
            if file["mimeType"] == "application/vnd.google-apps.folder" and not include_folders:
                continue
            current_path, path_note = _resolve_path(file, folder_cache, drive_service=drive_service)
            role, sensitivity, destination, confidence = classify_file(
                file.get("name", ""),
                file.get("mimeType", ""),
                current_path=current_path,
                media_policy=media_policy,
            )
            activity = {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}
            if activity_enrichment and activity_service:
                activity = enrich_activity(activity_service, file["id"])
            shortcut_target_id, shortcut_target_mime_type, shortcut_target_resource_key = _resolve_shortcut_details(file)
            capabilities = file.get("capabilities") or {}
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
                    current_path=current_path if not path_note else f"{current_path} [{path_note}]",
                    owned_by_me=str(bool(file.get("ownedByMe", False))),
                    capabilities_can_move_item_within_drive=str(bool(capabilities.get("canMoveItemWithinDrive", False))),
                    capabilities_can_move_item_out_of_drive=str(bool(capabilities.get("canMoveItemOutOfDrive", False))),
                    capabilities_can_add_my_drive_parent=str(bool(capabilities.get("canAddMyDriveParent", False))),
                    capabilities_can_remove_my_drive_parent=str(bool(capabilities.get("canRemoveMyDriveParent", False))),
                    is_shortcut=str(file.get("mimeType") == "application/vnd.google-apps.shortcut"),
                    shortcut_target_id=shortcut_target_id,
                    shortcut_target_mime_type=shortcut_target_mime_type,
                    shortcut_target_resource_key=shortcut_target_resource_key,
                    suggested_role=role,
                    suggested_sensitivity=sensitivity,
                    suggested_destination=destination,
                    suggested_confidence=confidence,
                    activity_level=activity["activity_level"],
                    last_activity_time=activity["last_activity_time"],
                    last_activity_type=activity["last_activity_type"],
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return rows
