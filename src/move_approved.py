from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .folder_setup import ensure_folder_path


PLAN_HEADER = [
    "timestamp",
    "mode",
    "outcome",
    "reason",
    "file_id",
    "name",
    "current_path",
    "original_parents",
    "destination_path",
    "destination_folder_id",
]


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


def _write_move_plan_row(plan_path: Path, *, mode: str, outcome: str, reason: str, file_id: str, name: str, current_path: str, original_parents: str, destination_path: str, destination_folder_id: str):
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    exists = plan_path.exists()
    with plan_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PLAN_HEADER)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "mode": mode,
                "outcome": outcome,
                "reason": reason,
                "file_id": file_id,
                "name": name,
                "current_path": current_path,
                "original_parents": original_parents,
                "destination_path": destination_path,
                "destination_folder_id": destination_folder_id,
            }
        )


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


def move_approved_rows(drive_service, sheets_service, spreadsheet_id: str, allow_create_missing_destination_folders: bool, allow_move_folders: bool, allow_move_shortcuts: bool, dry_run: bool, log_dir: str):
    from .sheets_review import read_review_rows

    rows = read_review_rows(sheets_service, spreadsheet_id)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    log_path = Path(log_dir) / f"move_log_{datetime.now().strftime('%Y-%m-%d')}.csv"
    plan_path = Path(log_dir) / f"move_plan_{timestamp}.csv"
    results = []
    evaluated_count = 0

    def record_skip(*, file_id: str, name: str, current_path: str, original_parents: str, destination_path: str, reason: str):
        _write_move_plan_row(
            plan_path,
            mode="DRY_RUN" if dry_run else "LIVE",
            outcome="SKIPPED",
            reason=reason,
            file_id=file_id,
            name=name,
            current_path=current_path,
            original_parents=original_parents,
            destination_path=destination_path,
            destination_folder_id="",
        )
        print(
            f"SKIPPED: {name} | current_path={current_path} | "
            f"destination={destination_path or ''} | file_id={file_id} | reason={reason}"
        )
        results.append((file_id, "skipped", reason))

    for row in rows:
        evaluated_count += 1
        file_id = row.get("file_id", "")
        name = row.get("name", "")
        current_path = row.get("current_path", "")
        original_parents = row.get("parents", "")
        destination = row.get("final_destination") or ""
        if row.get("review_decision", "") != "APPROVE_MOVE":
            record_skip(
                file_id=file_id,
                name=name,
                current_path=current_path,
                original_parents=original_parents,
                destination_path=destination,
                reason="review_decision is not APPROVE_MOVE",
            )
            continue
        if not file_id:
            record_skip(
                file_id="",
                name=name,
                current_path=current_path,
                original_parents=original_parents,
                destination_path=destination,
                reason="missing file_id",
            )
            continue
        if not row.get("final_destination", ""):
            record_skip(
                file_id=file_id,
                name=name,
                current_path=current_path,
                original_parents=original_parents,
                destination_path="",
                reason="final destination is blank",
            )
            continue
        if not destination:
            record_skip(
                file_id=file_id,
                name=name,
                current_path=current_path,
                original_parents=original_parents,
                destination_path="",
                reason="final destination is blank",
            )
            continue
        try:
            meta = drive_service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, parents, ownedByMe, capabilities(canMoveItemWithinDrive, canMoveItemOutOfDrive, canAddMyDriveParent, canRemoveMyDriveParent), shortcutDetails",
            ).execute()
            parents = meta.get("parents", []) or []
            capabilities = meta.get("capabilities") or {}
            shortcut_details = meta.get("shortcutDetails") or {}
            if not parents:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents="",
                    destination_path=destination,
                    reason="file has no parents",
                )
                continue
            if len(parents) > 1:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="file has multiple parents",
                )
                continue
            if meta.get("mimeType") == "application/vnd.google-apps.folder" and not allow_move_folders:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="file is a folder and moving folders is disabled",
                )
                continue
            if meta.get("mimeType") == "application/vnd.google-apps.shortcut":
                if not allow_move_shortcuts:
                    record_skip(
                        file_id=file_id,
                        name=meta.get("name", name),
                        current_path=current_path,
                        original_parents=",".join(parents),
                        destination_path=destination,
                        reason="shortcut moves disabled",
                    )
                    continue
                print(f"SHORTCUT: {meta.get('name', name)} | current_path={current_path} | destination={destination} | file_id={file_id}")
            if meta.get("ownedByMe") is False:
                if not (capabilities.get("canMoveItemWithinDrive") or capabilities.get("canMoveItemOutOfDrive")):
                    record_skip(
                        file_id=file_id,
                        name=meta.get("name", name),
                        current_path=current_path,
                        original_parents=",".join(parents),
                        destination_path=destination,
                        reason="file not owned by authenticated user",
                    )
                    continue
            dest_id = ensure_folder_path(drive_service, destination, allow_create_missing_destination_folders)
            if not dest_id:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="destination could not be resolved",
                )
                continue
            if not capabilities.get("canAddMyDriveParent", True):
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="cannot add destination parent",
                )
                continue
            if not capabilities.get("canRemoveMyDriveParent", True):
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="cannot remove existing parent",
                )
                continue
            if dry_run:
                _write_move_plan_row(
                    plan_path,
                    mode="DRY_RUN",
                    outcome="WOULD_MOVE",
                    reason="dry run",
                    file_id=file_id,
                    name=meta.get("name", row.get("name", "")),
                    current_path=row.get("current_path", ""),
                    original_parents=",".join(parents),
                    destination_path=destination,
                    destination_folder_id=dest_id,
                )
                print(
                    f"WOULD_MOVE: {meta.get('name', row.get('name', ''))} | "
                    f"current_path={current_path} | "
                    f"destination={destination} | "
                    f"file_id={file_id}"
                )
                results.append((file_id, "would_move", destination))
                continue
            previous_parents = ",".join(parents)
            drive_service.files().update(fileId=file_id, addParents=dest_id, removeParents=previous_parents, fields="id, parents").execute()
            _write_move_plan_row(
                plan_path,
                mode="LIVE",
                outcome="MOVED",
                reason="moved successfully",
                file_id=file_id,
                name=meta.get("name", row.get("name", "")),
                current_path=current_path,
                original_parents=previous_parents,
                destination_path=destination,
                destination_folder_id=dest_id,
            )
            print(
                f"MOVED: {meta.get('name', row.get('name', ''))} | "
                f"current_path={current_path} | "
                f"destination={destination} | "
                f"file_id={file_id}"
            )
            results.append((file_id, "moved", destination))
        except Exception as exc:
            _write_move_plan_row(
                plan_path,
                mode="DRY_RUN" if dry_run else "LIVE",
                outcome="ERROR",
                reason=str(exc),
                file_id=file_id,
                name=name,
                current_path=current_path,
                original_parents=original_parents,
                destination_path=destination,
                destination_folder_id="",
            )
            print(
                f"ERROR: {name} | "
                f"current_path={current_path} | "
                f"destination={destination} | "
                f"file_id={file_id} | reason={exc}"
            )
            results.append((file_id, "error", str(exc)))
    return results, plan_path, evaluated_count
