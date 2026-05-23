from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .folder_setup import ensure_folder_path


def _log_attempt(log_path: Path, row: dict, action: str, status: str, message: str):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "action", "file_id", "file_name", "destination", "dry_run", "status", "message"])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "file_id": row.get("file_id", ""),
            "file_name": row.get("name", ""),
            "destination": row.get("destination", ""),
            "dry_run": row.get("dry_run", ""),
            "status": status,
            "message": message,
        })


def log_inventory_action(log_path: Path, action: str, status: str, message: str):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "action", "file_id", "file_name", "destination", "dry_run", "status", "message"])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "file_id": "",
            "file_name": "",
            "destination": "",
            "dry_run": "",
            "status": status,
            "message": message,
        })


def move_approved_rows(drive_service, sheets_service, spreadsheet_id: str, allow_create_missing_destination_folders: bool, allow_move_folders: bool, dry_run: bool, log_dir: str):
    from .sheets_review import read_review_rows

    rows = read_review_rows(sheets_service, spreadsheet_id)
    log_path = Path(log_dir) / f"move_log_{datetime.now().strftime('%Y-%m-%d')}.csv"
    results = []
    for row in rows:
        if row.get("review_decision", "") != "APPROVE_MOVE":
            continue
        file_id = row.get("file_id", "")
        destination = row.get("final_destination") or row.get("suggested_destination") or ""
        row["destination"] = destination
        row["dry_run"] = str(dry_run)
        try:
            meta = drive_service.files().get(fileId=file_id, fields="id, name, mimeType, parents").execute()
            if meta.get("mimeType") == "application/vnd.google-apps.folder" and not allow_move_folders:
                _log_attempt(log_path, row, "move", "skipped", "Folders are disabled by config")
                results.append((file_id, "skipped", "folder move disabled"))
                continue
            dest_id = ensure_folder_path(drive_service, destination, allow_create_missing_destination_folders)
            if not dest_id:
                _log_attempt(log_path, row, "move", "skipped", "Destination folder not found and creation disabled")
                results.append((file_id, "skipped", "destination missing"))
                continue
            if dry_run:
                _log_attempt(log_path, row, "move", "dry_run", "No changes made")
                results.append((file_id, "dry_run", destination))
                continue
            previous_parents = ",".join(meta.get("parents", []))
            drive_service.files().update(fileId=file_id, addParents=dest_id, removeParents=previous_parents, fields="id, parents").execute()
            _log_attempt(log_path, row, "move", "success", "Moved")
            results.append((file_id, "success", destination))
        except Exception as exc:
            _log_attempt(log_path, row, "move", "error", str(exc))
            results.append((file_id, "error", str(exc)))
    return results
