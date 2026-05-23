from __future__ import annotations

import csv
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


def _log_bulk(log_path: Path, row: dict, destination: str, dry_run: bool, status: str, message: str):
    row = dict(row)
    row["destination"] = destination
    row["dry_run"] = str(dry_run)
    _log_attempt(log_path, row, "move", status, message)


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
        if not file_id:
            _log_bulk(log_path, row, "", dry_run, "skipped", "Missing file_id")
            results.append((file_id, "skipped", "missing file_id"))
            continue
        destination = row.get("final_destination") or row.get("suggested_destination") or ""
        if not destination:
            _log_bulk(log_path, row, "", dry_run, "skipped", "No destination was provided")
            results.append((file_id, "skipped", "missing destination"))
            continue
        try:
            meta = drive_service.files().get(fileId=file_id, fields="id, name, mimeType, parents").execute()
            if meta.get("mimeType") == "application/vnd.google-apps.folder" and not allow_move_folders:
                _log_bulk(log_path, row, destination, dry_run, "skipped", "Folders are disabled by config")
                results.append((file_id, "skipped", "folder move disabled"))
                continue
            dest_id = ensure_folder_path(drive_service, destination, allow_create_missing_destination_folders)
            if not dest_id:
                _log_bulk(log_path, row, destination, dry_run, "skipped", "Destination folder not found and creation disabled")
                results.append((file_id, "skipped", "destination missing"))
                continue
            parents = meta.get("parents", []) or []
            parent_count = len(parents)
            if parent_count == 0:
                _log_bulk(log_path, row, destination, dry_run, "skipped", "File has no parent folders")
                results.append((file_id, "skipped", "missing source parent"))
                continue
            if parent_count > 1:
                _log_bulk(log_path, row, destination, dry_run, "skipped", "File has multiple parents; review manually")
                results.append((file_id, "skipped", "multiple parents"))
                continue
            if dry_run:
                _log_bulk(log_path, row, destination, dry_run, "would_move", f"Would move to {destination}")
                results.append((file_id, "would_move", destination))
                continue
            previous_parents = ",".join(parents)
            drive_service.files().update(fileId=file_id, addParents=dest_id, removeParents=previous_parents, fields="id, parents").execute()
            _log_bulk(log_path, row, destination, dry_run, "moved", f"Moved to {destination}")
            results.append((file_id, "moved", destination))
        except Exception as exc:
            _log_bulk(log_path, row, destination, dry_run, "error", str(exc))
            results.append((file_id, "error", str(exc)))
    return results
