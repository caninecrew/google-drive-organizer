from __future__ import annotations

import csv
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from .move_approved import evaluate_move_eligibility


AUTO_APPROVAL_PLAN_HEADER = [
    "file_id",
    "name",
    "current_path",
    "suggested_role",
    "suggested_confidence",
    "suggested_sensitivity",
    "owned_by_me",
    "is_shortcut",
    "final_destination",
    "current_review_decision",
    "planned_review_decision",
    "reason",
]

FILL_DESTINATIONS_PLAN_HEADER = [
    "file_id",
    "name",
    "current_path",
    "mime_type",
    "suggested_role",
    "suggested_destination",
    "suggested_confidence",
    "suggested_sensitivity",
    "final_destination_current",
    "final_destination_planned",
    "review_decision_current",
    "review_decision_planned",
    "reason",
]

BULK_PREPARE_SAFE_PLAN_HEADER = [
    "file_id",
    "name",
    "current_path",
    "mime_type",
    "suggested_role",
    "suggested_destination",
    "suggested_confidence",
    "suggested_sensitivity",
    "owned_by_me",
    "is_shortcut",
    "final_destination_current",
    "final_destination_planned",
    "review_decision_current",
    "review_decision_planned",
    "reason",
]


def _read_sheet_rows(sheets_service, spreadsheet_id: str):
    result = sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="Sheet1!A1:ZZ").execute()
    values = result.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for offset, row in enumerate(values[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = offset
        rows.append(item)
    return headers, rows


def _truthy(value: str) -> bool:
    return str(value).strip().lower() == "true"


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _has_unknown_parent(current_path: str) -> bool:
    path = (current_path or "").lower()
    return "unknown parent" in path or "[unresolved parent]" in path


def _collect_bulk_risk_reasons(
    row: dict,
    *,
    include_medium_confidence: bool,
    include_low_confidence: bool,
    owned_only: bool,
    shared_file_strategy: str,
) -> list[str]:
    reasons: list[str] = []
    final_destination = row.get("final_destination", "").strip()
    if not final_destination:
        reasons.append("blank final_destination")
    confidence = row.get("suggested_confidence", "")
    if confidence == "Low":
        if not include_low_confidence:
            reasons.append("low confidence")
    elif confidence == "Medium":
        if not include_medium_confidence:
            reasons.append("medium confidence excluded")
    else:
        if confidence not in {"High", "Medium"}:
            reasons.append("low confidence")
    if row.get("suggested_sensitivity", "") != "Normal":
        reasons.append("non-normal sensitivity")
    owned_by_me = _truthy(row.get("owned_by_me", ""))
    if owned_only and not owned_by_me:
        reasons.append("owned-only")
    if not owned_by_me:
        if shared_file_strategy == "skip":
            reasons.append("not owned by me")
        elif shared_file_strategy == "allow-capable":
            capable = (
                _truthy(row.get("capabilities_can_move_item_within_drive", ""))
                and _truthy(row.get("capabilities_can_add_my_drive_parent", ""))
                and _truthy(row.get("capabilities_can_remove_my_drive_parent", ""))
            )
            if not capable:
                if not _truthy(row.get("capabilities_can_move_item_within_drive", "")):
                    reasons.append("missing capability: canMoveItemWithinDrive")
                if not _truthy(row.get("capabilities_can_add_my_drive_parent", "")):
                    reasons.append("missing capability: canAddMyDriveParent")
                if not _truthy(row.get("capabilities_can_remove_my_drive_parent", "")):
                    reasons.append("missing capability: canRemoveMyDriveParent")
        else:
            reasons.append("not owned by me")
    if _truthy(row.get("is_shortcut", "")):
        reasons.append("shortcut")
    if _has_unknown_parent(row.get("current_path", "")):
        reasons.append("unknown parent")
    if "untitled" in row.get("name", "").lower():
        reasons.append("untitled filename")
    if row.get("mime_type", "") == "application/vnd.google-apps.folder":
        reasons.append("folder")
    return reasons


def _is_safe_for_auto_approve(row: dict) -> tuple[bool, str]:
    reasons = _collect_bulk_risk_reasons(
        row,
        include_medium_confidence=True,
        include_low_confidence=False,
        owned_only=False,
        shared_file_strategy="skip",
    )
    if reasons:
        return False, "; ".join(reasons)
    return True, "safe"


def _plan_review_decision(row: dict) -> tuple[str, str]:
    safe, reason = _is_safe_for_auto_approve(row)
    if safe:
        return "APPROVE_MOVE", "safe"
    reason_bits = {part.strip() for part in reason.split(";") if part.strip()}
    if reason_bits & {"low confidence", "medium confidence excluded", "non-normal sensitivity", "unknown parent", "shortcut", "not owned by me", "missing move capability", "untitled filename", "blank final_destination", "folder", "owned-only", "missing capability: canMoveItemWithinDrive", "missing capability: canAddMyDriveParent", "missing capability: canRemoveMyDriveParent"}:
        return "NEEDS_REVIEW", reason
    return "REVIEW", reason


def _write_plan_csv(plan_path: Path, rows: list[dict]):
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with plan_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=AUTO_APPROVAL_PLAN_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _write_fill_plan_csv(plan_path: Path, rows: list[dict]):
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with plan_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FILL_DESTINATIONS_PLAN_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _write_bulk_plan_csv(plan_path: Path, rows: list[dict]):
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with plan_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BULK_PREPARE_SAFE_PLAN_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _is_retryable_exception(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "status", None)
    if status is None and hasattr(exc, "resp"):
        status = getattr(getattr(exc, "resp"), "status", None)
    return status in {429, 500, 502, 503, 504}


def _retryable_request(request_fn, description: str, max_attempts: int = 5):
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            return request_fn()
        except Exception as exc:
            if not _is_retryable_exception(exc) or attempt >= max_attempts:
                raise
            jitter = random.uniform(0, delay * 0.25)
            sleep_for = delay + jitter
            print(f"Retrying {description} after rate limit/transient error: attempt {attempt}/{max_attempts}, sleeping {sleep_for:.2f}s")
            time.sleep(sleep_for)
            delay = min(delay * 2, 30)


def _sheet_batch_update_values(sheets_service, spreadsheet_id: str, data: list[dict]):
    if not data:
        return None

    def _call():
        return sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()

    return _retryable_request(_call, "Sheets batchUpdate")


def auto_approve_safe(sheets_service, spreadsheet_id: str, log_dir: str, dry_run: bool, max_approve: int | None = None):
    headers, rows = _read_sheet_rows(sheets_service, spreadsheet_id)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    plan_path = Path(log_dir) / f"auto_approval_plan_{timestamp}.csv"
    plan_rows = []
    approve_count = 0
    needs_review_count = 0
    unchanged_count = 0
    total_rows = 0
    reasons = Counter()
    updates = []
    review_column = None
    if headers and "review_decision" in headers:
        review_column = _column_letter(headers.index("review_decision"))

    for row in rows:
        total_rows += 1
        current = row.get("review_decision", "")
        planned, reason = _plan_review_decision(row)
        if planned == "APPROVE_MOVE" and max_approve is not None and approve_count >= max_approve:
            planned = "REVIEW"
            reason = "max approvals reached"
        if planned == "APPROVE_MOVE":
            approve_count += 1
            if current == "APPROVE_MOVE":
                unchanged_count += 1
            elif not dry_run:
                updates.append((row["_row_number"], planned))
        elif planned == "NEEDS_REVIEW":
            needs_review_count += 1
            if current == "NEEDS_REVIEW":
                unchanged_count += 1
            elif not dry_run:
                updates.append((row["_row_number"], planned))
        else:
            unchanged_count += 1
        reasons[reason] += 1
        plan_rows.append(
            {
                "file_id": row.get("file_id", ""),
                "name": row.get("name", ""),
                "current_path": row.get("current_path", ""),
                "suggested_role": row.get("suggested_role", ""),
                "suggested_confidence": row.get("suggested_confidence", ""),
                "suggested_sensitivity": row.get("suggested_sensitivity", ""),
                "owned_by_me": row.get("owned_by_me", ""),
                "is_shortcut": row.get("is_shortcut", ""),
                "final_destination": row.get("final_destination", ""),
                "current_review_decision": current,
                "planned_review_decision": planned,
                "reason": reason,
            }
        )
    _write_plan_csv(plan_path, plan_rows)
    if not dry_run:
        for row_number, decision in updates:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"Sheet1!{review_column or 'AB'}{row_number}",
                valueInputOption="RAW",
                body={"values": [[decision]]},
            ).execute()
    return {
        "total_rows": total_rows,
        "approve_count": approve_count,
        "needs_review_count": needs_review_count,
        "unchanged_count": unchanged_count,
        "top_reasons": reasons.most_common(5),
        "plan_path": plan_path,
        "updated_rows": len(updates),
    }


def _is_media_like(row: dict) -> bool:
    text = " ".join([row.get("name", ""), row.get("current_path", ""), row.get("mime_type", ""), row.get("suggested_role", "")]).lower()
    return any(token in text for token in ["photo", "video", "image", "jpg", "jpeg", "png", "heic", "mp4", "mov"])


def _safe_fill_destination(row: dict) -> tuple[str, str]:
    current = row.get("final_destination", "").strip()
    if current:
        return current, "existing final_destination preserved"
    role = row.get("suggested_role", "")
    text = " ".join([row.get("name", ""), row.get("current_path", "")]).lower()
    media_policy = "role_first"
    if "family history videos" in text:
        return "01 Personal/Family History/Video Interviews", "family history videos"
    if "foia" in text or "public records" in text or "open records" in text:
        return "06 FOIA and Public Records", "foia/public records"
    if _is_media_like(row):
        if "scouting" in text:
            return "04 Scouting/Photos", "scouting media"
        if "church" in text or "ministry" in text or "sermon" in text:
            return "05 Church and Ministry", "church media"
        if media_policy == "role_first":
            if role == "Scouting":
                return "04 Scouting/Photos", "role-first scouting media"
            if role == "Church and Ministry":
                return "05 Church and Ministry", "role-first church media"
            if role == "Personal":
                return "01 Personal/Family History/Video Interviews", "role-first family history media"
        return "08 Photos and Media", "generic media"
    suggested = row.get("suggested_destination", "").strip()
    if suggested:
        return suggested, "suggested_destination"
    return "", "no safe destination"


def fill_destinations(sheets_service, spreadsheet_id: str, log_dir: str, dry_run: bool):
    headers, rows = _read_sheet_rows(sheets_service, spreadsheet_id)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    plan_path = Path(log_dir) / f"fill_destinations_plan_{timestamp}.csv"
    plan_rows = []
    updates = []
    total_rows = 0
    filled_count = 0
    already_filled_count = 0
    still_blank_count = 0
    destination_counts = Counter()
    reasons = Counter()
    review_column = None
    destination_column = None
    if headers and "review_decision" in headers:
        review_column = _column_letter(headers.index("review_decision"))
    if headers and "final_destination" in headers:
        destination_column = _column_letter(headers.index("final_destination"))
    planned_update_ranges = 0

    for row in rows:
        total_rows += 1
        current_final = row.get("final_destination", "").strip()
        current_review = row.get("review_decision", "").strip()
        planned_final, reason = _safe_fill_destination(row)
        planned_review = current_review or "REVIEW"
        if current_final:
            already_filled_count += 1
            planned_final = current_final
        elif planned_final:
            filled_count += 1
            destination_counts[planned_final] += 1
            if not dry_run:
                updates.append((row["_row_number"], planned_final, planned_review))
                planned_update_ranges += 1
        else:
            still_blank_count += 1
        if not planned_final:
            reasons[reason] += 1
        elif current_final:
            reasons["existing final_destination preserved"] += 1
        else:
            reasons[reason] += 1
        plan_rows.append(
            {
                "file_id": row.get("file_id", ""),
                "name": row.get("name", ""),
                "current_path": row.get("current_path", ""),
                "mime_type": row.get("mime_type", ""),
                "suggested_role": row.get("suggested_role", ""),
                "suggested_destination": row.get("suggested_destination", ""),
                "suggested_confidence": row.get("suggested_confidence", ""),
                "suggested_sensitivity": row.get("suggested_sensitivity", ""),
                "final_destination_current": current_final,
                "final_destination_planned": planned_final,
                "review_decision_current": current_review,
                "review_decision_planned": planned_review,
                "reason": reason if not current_final else "existing final_destination preserved",
            }
        )
    _write_fill_plan_csv(plan_path, plan_rows)
    if not dry_run:
        batch_updates = []
        for row_number, destination, review_decision in updates:
            if destination_column:
                batch_updates.append({"range": f"Sheet1!{destination_column}{row_number}", "values": [[destination]]})
            if review_column and not rows[row_number - 2].get("review_decision", "").strip():
                batch_updates.append({"range": f"Sheet1!{review_column}{row_number}", "values": [[review_decision]]})
        batch_call_count = 1 if batch_updates else 0
        _sheet_batch_update_values(sheets_service, spreadsheet_id, batch_updates)
    else:
        batch_call_count = 0
    return {
        "total_rows": total_rows,
        "filled_count": filled_count,
        "already_filled_count": already_filled_count,
        "still_blank_count": still_blank_count,
        "top_destinations": destination_counts.most_common(5),
        "top_reasons": reasons.most_common(5),
        "plan_path": plan_path,
        "updated_rows": len(updates),
        "planned_update_ranges": planned_update_ranges,
        "batch_calls_sent": batch_call_count,
    }


def _planned_destination_for_bulk(row: dict) -> tuple[str, str]:
    current = row.get("final_destination", "").strip()
    if current:
        return current, "existing final_destination preserved"
    planned, reason = _safe_fill_destination(row)
    return planned, reason


def _safe_to_approve_bulk(
    row: dict,
    planned_final_destination: str,
    include_medium_confidence: bool,
    include_low_confidence: bool,
    owned_only: bool,
    shared_file_strategy: str,
) -> tuple[bool, list[str]]:
    reasons = _collect_bulk_risk_reasons(
        {**row, "final_destination": planned_final_destination},
        include_medium_confidence=include_medium_confidence,
        include_low_confidence=include_low_confidence,
        owned_only=owned_only,
        shared_file_strategy=shared_file_strategy,
    )
    if not planned_final_destination:
        reasons.insert(0, "blank final_destination")
    return (len(reasons) == 0), reasons


def bulk_prepare_safe(
    sheets_service,
    spreadsheet_id: str,
    log_dir: str,
    dry_run: bool,
    include_medium_confidence: bool = True,
    include_low_confidence: bool = False,
    limit: int | None = None,
    shared_file_strategy: str = "skip",
    owned_only: bool = False,
    drive_service=None,
):
    headers, rows = _read_sheet_rows(sheets_service, spreadsheet_id)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    plan_path = Path(log_dir) / f"bulk_prepare_safe_plan_{timestamp}.csv"
    plan_rows = []
    batch_updates = []
    total_rows = 0
    filled_count = 0
    approve_count = 0
    needs_review_count = 0
    unchanged_count = 0
    reasons = Counter()
    destination_counts = Counter()
    owned_true_count = 0
    owned_false_count = 0
    all_capable_true_count = 0
    blocked_only_by_not_owned = 0
    blocked_by_low_confidence = 0
    blocked_by_sensitivity = 0
    planned_reason_rows = []
    planned_update_ranges = 0
    review_column = None
    destination_column = None
    if headers and "review_decision" in headers:
        review_column = _column_letter(headers.index("review_decision"))
    if headers and "final_destination" in headers:
        destination_column = _column_letter(headers.index("final_destination"))

    approved_seen = 0
    for row in rows:
        total_rows += 1
        current_final = row.get("final_destination", "").strip()
        current_review = row.get("review_decision", "").strip()
        planned_destination, destination_reason = _planned_destination_for_bulk(row)
        planned_final = current_final or planned_destination
        if not current_final and planned_destination:
            filled_count += 1
            destination_counts[planned_destination] += 1
        owned_by_me = _truthy(row.get("owned_by_me", ""))
        if owned_by_me:
            owned_true_count += 1
        else:
            owned_false_count += 1
        all_capable_true = (
            _truthy(row.get("capabilities_can_move_item_within_drive", ""))
            and _truthy(row.get("capabilities_can_add_my_drive_parent", ""))
            and _truthy(row.get("capabilities_can_remove_my_drive_parent", ""))
        )
        if all_capable_true:
            all_capable_true_count += 1
        safe, approval_reasons = _safe_to_approve_bulk(
            row,
            planned_final,
            include_medium_confidence,
            include_low_confidence,
            owned_only,
            shared_file_strategy,
        )
        destination_folder_id = ""
        destination_eligible = False
        destination_reasons: list[str] = []
        if planned_final and drive_service is not None:
            try:
                from .folder_setup import ensure_folder_path

                destination_folder_id = ensure_folder_path(drive_service, planned_final, False)
            except Exception:
                destination_folder_id = ""
            destination_eligible, destination_reasons = evaluate_move_eligibility(
                {
                    **row,
                    "file_id": row.get("file_id", ""),
                    "review_decision": "APPROVE_MOVE" if safe else "NEEDS_REVIEW",
                },
                destination_path=planned_final,
                destination_folder_id=destination_folder_id or "",
                original_parents=(row.get("parents", "") or "").split(",") if row.get("parents", "") else [],
                allow_move_folders=False,
                allow_move_shortcuts=False,
                shared_file_strategy=shared_file_strategy,
                owned_only=owned_only,
                current_metadata={
                    "ownedByMe": row.get("owned_by_me", ""),
                    "capabilities": {
                        "canMoveItemWithinDrive": row.get("capabilities_can_move_item_within_drive", ""),
                        "canMoveItemOutOfDrive": row.get("capabilities_can_move_item_out_of_drive", ""),
                        "canAddMyDriveParent": row.get("capabilities_can_add_my_drive_parent", ""),
                        "canRemoveMyDriveParent": row.get("capabilities_can_remove_my_drive_parent", ""),
                    },
                    "mimeType": row.get("mime_type", ""),
                },
            )
            if not destination_eligible:
                if "destination folder could not be resolved" not in destination_reasons:
                    approval_reasons = destination_reasons + approval_reasons
                else:
                    approval_reasons = destination_reasons
                safe = False
        reason_parts = [destination_reason] if destination_reason else []
        if safe and (limit is None or approved_seen < limit):
            planned_review = "APPROVE_MOVE"
            approved_seen += 1
            reason_parts.append("safe")
        elif safe:
            planned_review = current_review
            reason_parts.append("max approvals reached")
        else:
            planned_review = "NEEDS_REVIEW" if current_review != "NEEDS_REVIEW" else current_review
            reason_parts.extend(approval_reasons)
            if "not owned by me" in approval_reasons and len(approval_reasons) == 1:
                blocked_only_by_not_owned += 1
            if "low confidence" in approval_reasons:
                blocked_by_low_confidence += 1
            if "non-normal sensitivity" in approval_reasons:
                blocked_by_sensitivity += 1

        destination_changed = not current_final and bool(planned_destination)
        review_changed = planned_review != current_review

        if planned_review == "APPROVE_MOVE":
            approve_count += 1
        elif planned_review == "NEEDS_REVIEW":
            needs_review_count += 1
        else:
            unchanged_count += 1

        if not destination_changed and not review_changed:
            reason = "unchanged"
        else:
            reason = "; ".join([part for part in reason_parts if part]) or "safe"

        if not current_final and planned_destination:
            final_destination_planned = planned_destination
        else:
            final_destination_planned = current_final

        if destination_changed and destination_column and not dry_run:
            batch_updates.append(
                {"range": f"Sheet1!{destination_column}{row['_row_number']}", "values": [[planned_destination]]}
            )
        if review_changed and review_column and not dry_run:
            batch_updates.append(
                {"range": f"Sheet1!{review_column}{row['_row_number']}", "values": [[planned_review]]}
            )

        if destination_changed or review_changed:
            if destination_changed:
                planned_update_ranges += 1
            if review_changed:
                planned_update_ranges += 1
        plan_rows.append(
            {
                "file_id": row.get("file_id", ""),
                "name": row.get("name", ""),
                "current_path": row.get("current_path", ""),
                "mime_type": row.get("mime_type", ""),
                "suggested_role": row.get("suggested_role", ""),
                "suggested_destination": row.get("suggested_destination", ""),
                "suggested_confidence": row.get("suggested_confidence", ""),
                "suggested_sensitivity": row.get("suggested_sensitivity", ""),
                "owned_by_me": row.get("owned_by_me", ""),
                "is_shortcut": row.get("is_shortcut", ""),
                "final_destination_current": current_final,
                "final_destination_planned": final_destination_planned,
                "review_decision_current": current_review,
                "review_decision_planned": planned_review,
                "reason": reason,
            }
        )
        reasons.update([part for part in reason_parts if part] or [reason])
        planned_reason_rows.append(reason)
    _write_bulk_plan_csv(plan_path, plan_rows)
    if not dry_run:
        _sheet_batch_update_values(sheets_service, spreadsheet_id, batch_updates)
    return {
        "total_rows": total_rows,
        "filled_count": filled_count,
        "approve_count": approve_count,
        "needs_review_count": needs_review_count,
        "unchanged_count": unchanged_count,
        "owned_true_count": owned_true_count,
        "owned_false_count": owned_false_count,
        "all_capable_true_count": all_capable_true_count,
        "blocked_only_by_not_owned": blocked_only_by_not_owned,
        "blocked_by_low_confidence": blocked_by_low_confidence,
        "blocked_by_sensitivity": blocked_by_sensitivity,
        "top_destinations": destination_counts.most_common(5),
        "top_reasons": reasons.most_common(5),
        "plan_path": plan_path,
        "updated_rows": len(batch_updates),
        "planned_update_ranges": planned_update_ranges,
        "batch_calls_sent": 1 if (batch_updates and not dry_run) else 0,
    }
