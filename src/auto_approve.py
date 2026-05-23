from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path


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


def _is_safe_for_auto_approve(row: dict) -> tuple[bool, str]:
    file_id = row.get("file_id", "")
    if not file_id:
        return False, "missing file_id"
    if not row.get("final_destination", "").strip():
        return False, "blank final_destination"
    if row.get("suggested_confidence", "") not in {"High", "Medium"}:
        return False, "low confidence"
    if row.get("suggested_sensitivity", "") != "Normal":
        return False, "non-normal sensitivity"
    if not _truthy(row.get("owned_by_me", "")):
        return False, "not owned by me"
    if _truthy(row.get("is_shortcut", "")):
        return False, "shortcut"
    if _has_unknown_parent(row.get("current_path", "")):
        return False, "unknown parent"
    if "untitled" in row.get("name", "").lower():
        return False, "untitled filename"
    if row.get("mime_type", "") == "application/vnd.google-apps.folder":
        return False, "folder"
    if "capabilities_can_move_item_within_drive" in row and not _truthy(row.get("capabilities_can_move_item_within_drive", "")):
        return False, "missing move capability"
    if "capabilities_can_add_my_drive_parent" in row and not _truthy(row.get("capabilities_can_add_my_drive_parent", "")):
        return False, "missing move capability"
    if "capabilities_can_remove_my_drive_parent" in row and not _truthy(row.get("capabilities_can_remove_my_drive_parent", "")):
        return False, "missing move capability"
    return True, "safe"


def _plan_review_decision(row: dict) -> tuple[str, str]:
    safe, reason = _is_safe_for_auto_approve(row)
    if safe:
        return "APPROVE_MOVE", "safe"
    if reason in {"low confidence", "non-normal sensitivity", "unknown parent", "shortcut", "not owned by me", "missing move capability", "untitled filename", "blank final_destination"}:
        return "NEEDS_REVIEW", reason
    return "REVIEW", reason


def _write_plan_csv(plan_path: Path, rows: list[dict]):
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with plan_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=AUTO_APPROVAL_PLAN_HEADER)
        writer.writeheader()
        writer.writerows(rows)


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
