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
    "review_decision",
    "owned_by_me",
    "capabilities_can_move_item_within_drive",
    "capabilities_can_add_my_drive_parent",
    "capabilities_can_remove_my_drive_parent",
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


def _write_move_plan_row(
    plan_path: Path,
    *,
    mode: str,
    outcome: str,
    reason: str,
    file_id: str,
    name: str,
    current_path: str,
    review_decision: str,
    owned_by_me: str,
    capabilities_can_move_item_within_drive: str,
    capabilities_can_add_my_drive_parent: str,
    capabilities_can_remove_my_drive_parent: str,
    original_parents: str,
    destination_path: str,
    destination_folder_id: str,
):
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
                "review_decision": review_decision,
                "owned_by_me": owned_by_me,
                "capabilities_can_move_item_within_drive": capabilities_can_move_item_within_drive,
                "capabilities_can_add_my_drive_parent": capabilities_can_add_my_drive_parent,
                "capabilities_can_remove_my_drive_parent": capabilities_can_remove_my_drive_parent,
                "original_parents": original_parents,
                "destination_path": destination_path,
                "destination_folder_id": destination_folder_id,
            }
        )


def _value_is_blank(value: str) -> bool:
    return str(value).strip() == ""


def _capability_value(row_or_meta: dict, key: str) -> str:
    value = row_or_meta.get(key, "")
    if value is None:
        return ""
    return str(value).strip()


def evaluate_move_eligibility(
    row: dict,
    *,
    destination_path: str,
    destination_folder_id: str = "",
    original_parents: list[str] | tuple[str, ...] | None = None,
    allow_move_folders: bool = False,
    allow_move_shortcuts: bool = False,
    shared_file_strategy: str = "skip",
    owned_only: bool = False,
    current_metadata: dict | None = None,
):
    meta = current_metadata or row
    reasons: list[str] = []
    if not row.get("file_id", "").strip():
        reasons.append("missing file_id")
    if not str(row.get("review_decision", "")).strip() == "APPROVE_MOVE":
        reasons.append("review_decision is not APPROVE_MOVE")
    if _value_is_blank(destination_path):
        reasons.append("final destination is blank")
    if _value_is_blank(destination_folder_id):
        reasons.append("destination folder could not be resolved")
    parents = list(original_parents or [])
    if not parents:
        reasons.append("file has no parents")
    if len(parents) > 1:
        reasons.append("file has multiple parents")
    mime_type = str(meta.get("mimeType", row.get("mime_type", "")))
    if mime_type == "application/vnd.google-apps.folder" and not allow_move_folders:
        reasons.append("file is a folder and moving folders is disabled")
    if mime_type == "application/vnd.google-apps.shortcut" and not allow_move_shortcuts:
        reasons.append("shortcut moves disabled")

    owned_by_me = str(meta.get("ownedByMe", row.get("owned_by_me", ""))).strip().lower() == "true"
    can_move_within_drive = _capability_value(meta, "capabilities_can_move_item_within_drive") or str((meta.get("capabilities") or {}).get("canMoveItemWithinDrive", "")).strip()
    can_move_out_of_drive = _capability_value(meta, "capabilities_can_move_item_out_of_drive") or str((meta.get("capabilities") or {}).get("canMoveItemOutOfDrive", "")).strip()
    can_add_parent = _capability_value(meta, "capabilities_can_add_my_drive_parent") or str((meta.get("capabilities") or {}).get("canAddMyDriveParent", "")).strip()
    can_remove_parent = _capability_value(meta, "capabilities_can_remove_my_drive_parent") or str((meta.get("capabilities") or {}).get("canRemoveMyDriveParent", "")).strip()
    capability_fields_present = any(
        _capability_value(meta, key) for key in [
            "capabilities_can_move_item_within_drive",
            "capabilities_can_move_item_out_of_drive",
            "capabilities_can_add_my_drive_parent",
            "capabilities_can_remove_my_drive_parent",
        ]
    ) or bool(meta.get("capabilities"))
    if owned_only and not owned_by_me:
        reasons.append("owned-only")
    elif not owned_by_me:
        if shared_file_strategy == "skip":
            reasons.append("file not owned by authenticated user")
        elif shared_file_strategy == "allow-capable":
            if not (str(can_move_within_drive).lower() == "true" and str(can_add_parent).lower() == "true" and str(can_remove_parent).lower() == "true"):
                if capability_fields_present:
                    if str(can_move_within_drive).lower() != "true":
                        reasons.append("missing capability: canMoveItemWithinDrive")
                    if str(can_add_parent).lower() != "true":
                        reasons.append("missing capability: canAddMyDriveParent")
                    if str(can_remove_parent).lower() != "true":
                        reasons.append("missing capability: canRemoveMyDriveParent")
                else:
                    reasons.append("move capability not available")
        else:
            reasons.append("file not owned by authenticated user")
    else:
        if str(can_move_within_drive).lower() != "true":
            reasons.append("move capability not available")
        elif str(can_remove_parent).lower() != "true":
            reasons.append("cannot remove existing parent")

    deduped = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return len(deduped) == 0, deduped


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

    def record_skip(
        *,
        file_id: str,
        name: str,
        current_path: str,
        review_decision: str,
        owned_by_me: str,
        capabilities_can_move_item_within_drive: str,
        capabilities_can_add_my_drive_parent: str,
        capabilities_can_remove_my_drive_parent: str,
        original_parents: str,
        destination_path: str,
        destination_folder_id: str = "",
        reason: str,
    ):
        _write_move_plan_row(
            plan_path,
            mode="DRY_RUN" if dry_run else "LIVE",
            outcome="SKIPPED",
            reason=reason,
            file_id=file_id,
            name=name,
            current_path=current_path,
            review_decision=review_decision,
            owned_by_me=owned_by_me,
            capabilities_can_move_item_within_drive=capabilities_can_move_item_within_drive,
            capabilities_can_add_my_drive_parent=capabilities_can_add_my_drive_parent,
            capabilities_can_remove_my_drive_parent=capabilities_can_remove_my_drive_parent,
            original_parents=original_parents,
            destination_path=destination_path,
            destination_folder_id=destination_folder_id,
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
        review_decision = row.get("review_decision", "")
        original_parents = row.get("parents", "")
        destination = row.get("final_destination") or ""
        if row.get("review_decision", "") != "APPROVE_MOVE":
            record_skip(
                file_id=file_id,
                name=name,
                current_path=current_path,
                review_decision=review_decision,
                owned_by_me=row.get("owned_by_me", ""),
                capabilities_can_move_item_within_drive=row.get("capabilities_can_move_item_within_drive", ""),
                capabilities_can_add_my_drive_parent=row.get("capabilities_can_add_my_drive_parent", ""),
                capabilities_can_remove_my_drive_parent=row.get("capabilities_can_remove_my_drive_parent", ""),
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
                review_decision=review_decision,
                owned_by_me=row.get("owned_by_me", ""),
                capabilities_can_move_item_within_drive=row.get("capabilities_can_move_item_within_drive", ""),
                capabilities_can_add_my_drive_parent=row.get("capabilities_can_add_my_drive_parent", ""),
                capabilities_can_remove_my_drive_parent=row.get("capabilities_can_remove_my_drive_parent", ""),
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
                review_decision=review_decision,
                owned_by_me=row.get("owned_by_me", ""),
                capabilities_can_move_item_within_drive=row.get("capabilities_can_move_item_within_drive", ""),
                capabilities_can_add_my_drive_parent=row.get("capabilities_can_add_my_drive_parent", ""),
                capabilities_can_remove_my_drive_parent=row.get("capabilities_can_remove_my_drive_parent", ""),
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
                review_decision=review_decision,
                owned_by_me=row.get("owned_by_me", ""),
                capabilities_can_move_item_within_drive=row.get("capabilities_can_move_item_within_drive", ""),
                capabilities_can_add_my_drive_parent=row.get("capabilities_can_add_my_drive_parent", ""),
                capabilities_can_remove_my_drive_parent=row.get("capabilities_can_remove_my_drive_parent", ""),
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
            dest_id = ensure_folder_path(drive_service, destination, allow_create_missing_destination_folders)
            eligible, eligibility_reasons = evaluate_move_eligibility(
                {
                    **row,
                    "file_id": file_id,
                    "review_decision": row.get("review_decision", ""),
                    "owned_by_me": str(meta.get("ownedByMe", row.get("owned_by_me", ""))),
                    "capabilities_can_move_item_within_drive": str(capabilities.get("canMoveItemWithinDrive", row.get("capabilities_can_move_item_within_drive", ""))),
                    "capabilities_can_move_item_out_of_drive": str(capabilities.get("canMoveItemOutOfDrive", row.get("capabilities_can_move_item_out_of_drive", ""))),
                    "capabilities_can_add_my_drive_parent": str(capabilities.get("canAddMyDriveParent", row.get("capabilities_can_add_my_drive_parent", ""))),
                    "capabilities_can_remove_my_drive_parent": str(capabilities.get("canRemoveMyDriveParent", row.get("capabilities_can_remove_my_drive_parent", ""))),
                    "mime_type": meta.get("mimeType", row.get("mime_type", "")),
                },
                destination_path=destination,
                destination_folder_id=dest_id or "",
                original_parents=parents,
                allow_move_folders=allow_move_folders,
                allow_move_shortcuts=allow_move_shortcuts,
                shared_file_strategy="skip",
                owned_only=False,
                current_metadata=meta,
            )
            if not dest_id:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    review_decision=review_decision,
                    owned_by_me=str(meta.get("ownedByMe", row.get("owned_by_me", ""))),
                    capabilities_can_move_item_within_drive=str(capabilities.get("canMoveItemWithinDrive", row.get("capabilities_can_move_item_within_drive", ""))),
                    capabilities_can_add_my_drive_parent=str(capabilities.get("canAddMyDriveParent", row.get("capabilities_can_add_my_drive_parent", ""))),
                    capabilities_can_remove_my_drive_parent=str(capabilities.get("canRemoveMyDriveParent", row.get("capabilities_can_remove_my_drive_parent", ""))),
                    original_parents=",".join(parents),
                    destination_path=destination,
                    reason="destination folder could not be resolved",
                )
                continue
            if not eligible:
                record_skip(
                    file_id=file_id,
                    name=meta.get("name", name),
                    current_path=current_path,
                    review_decision=review_decision,
                    owned_by_me=str(meta.get("ownedByMe", row.get("owned_by_me", ""))),
                    capabilities_can_move_item_within_drive=str(capabilities.get("canMoveItemWithinDrive", row.get("capabilities_can_move_item_within_drive", ""))),
                    capabilities_can_add_my_drive_parent=str(capabilities.get("canAddMyDriveParent", row.get("capabilities_can_add_my_drive_parent", ""))),
                    capabilities_can_remove_my_drive_parent=str(capabilities.get("canRemoveMyDriveParent", row.get("capabilities_can_remove_my_drive_parent", ""))),
                    original_parents=",".join(parents),
                    destination_path=destination,
                    destination_folder_id=dest_id,
                    reason="; ".join(eligibility_reasons),
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
                    review_decision=review_decision,
                    owned_by_me=str(meta.get("ownedByMe", row.get("owned_by_me", ""))),
                    capabilities_can_move_item_within_drive=str(capabilities.get("canMoveItemWithinDrive", row.get("capabilities_can_move_item_within_drive", ""))),
                    capabilities_can_add_my_drive_parent=str(capabilities.get("canAddMyDriveParent", row.get("capabilities_can_add_my_drive_parent", ""))),
                    capabilities_can_remove_my_drive_parent=str(capabilities.get("canRemoveMyDriveParent", row.get("capabilities_can_remove_my_drive_parent", ""))),
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
                review_decision=review_decision,
                owned_by_me=str(meta.get("ownedByMe", row.get("owned_by_me", ""))),
                capabilities_can_move_item_within_drive=str(capabilities.get("canMoveItemWithinDrive", row.get("capabilities_can_move_item_within_drive", ""))),
                capabilities_can_add_my_drive_parent=str(capabilities.get("canAddMyDriveParent", row.get("capabilities_can_add_my_drive_parent", ""))),
                capabilities_can_remove_my_drive_parent=str(capabilities.get("canRemoveMyDriveParent", row.get("capabilities_can_remove_my_drive_parent", ""))),
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
                review_decision=review_decision,
                owned_by_me=row.get("owned_by_me", ""),
                capabilities_can_move_item_within_drive=row.get("capabilities_can_move_item_within_drive", ""),
                capabilities_can_add_my_drive_parent=row.get("capabilities_can_add_my_drive_parent", ""),
                capabilities_can_remove_my_drive_parent=row.get("capabilities_can_remove_my_drive_parent", ""),
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
