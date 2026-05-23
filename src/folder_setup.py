from __future__ import annotations

FOLDER_PATHS = [
    "00 Inbox",
    "01 Personal",
    "02 School and Education",
    "03 Work and Career",
    "04 Scouting",
    "05 Church and Ministry",
    "06 FOIA and Public Records",
    "07 Projects and Coding",
    "08 Photos and Media",
    "09 Archive",
    "09 Archive/Childhood and Old Personal Files",
    "09 Archive/Old Random Files",
    "09 Archive/Old Games and Creative Projects",
    "09 Archive/Delete Later Review",
    "99 Review Later",
    "09 Archive/Imports/From germanshepherd999 Google Drive",
    "09 Archive/Imports/From TTU OneDrive",
    "09 Archive/Imports/From Personal OneDrive Cleanup",
]


def ensure_folder_path(drive_service, path: str, allow_create: bool):
    parent_id = "root"
    for part in path.split("/"):
        safe_part = part.replace("'", "\\'")
        query = (
            "trashed = false and mimeType = 'application/vnd.google-apps.folder' "
            f"and name = '{safe_part}' and '{parent_id}' in parents"
        )
        existing = (
            drive_service.files()
            .list(q=query, fields="files(id, name)", spaces="drive")
            .execute()
            .get("files", [])
        )
        if existing:
            parent_id = existing[0]["id"]
            continue
        if not allow_create:
            return None
        created = (
            drive_service.files()
            .create(
                body={
                    "name": part,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id],
                },
                fields="id",
            )
            .execute()
        )
        parent_id = created["id"]
    return parent_id
