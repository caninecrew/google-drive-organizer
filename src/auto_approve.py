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
        for row_number, destination, review_decision in updates:
            if destination_column:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Sheet1!{destination_column}{row_number}",
                    valueInputOption="RAW",
                    body={"values": [[destination]]},
                ).execute()
            if review_column and not rows[row_number - 2].get("review_decision", "").strip():
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Sheet1!{review_column}{row_number}",
                    valueInputOption="RAW",
                    body={"values": [[review_decision]]},
                ).execute()
    return {
        "total_rows": total_rows,
        "filled_count": filled_count,
        "already_filled_count": already_filled_count,
        "still_blank_count": still_blank_count,
        "top_destinations": destination_counts.most_common(5),
        "top_reasons": reasons.most_common(5),
        "plan_path": plan_path,
        "updated_rows": len(updates),
    }


def _planned_destination_for_bulk(row: dict) -> tuple[str, str]:
    current = row.get("final_destination", "").strip()
    if current:
        return current, "existing final_destination preserved"
    planned, reason = _safe_fill_destination(row)
    return planned, reason


def _safe_to_approve_bulk(row: dict, planned_final_destination: str, include_medium_confidence: bool, include_low_confidence: bool) -> tuple[bool, str]:
    if not planned_final_destination:
        return False, "blank final_destination"
    confidence = row.get("suggested_confidence", "")
    if confidence == "Low" and not include_low_confidence:
        return False, "low confidence"
    if confidence == "Medium" and not include_medium_confidence:
        return False, "medium confidence excluded"
    safe, reason = _is_safe_for_auto_approve({**row, "final_destination": planned_final_destination})
    return safe, reason


def bulk_prepare_safe(
    sheets_service,
    spreadsheet_id: str,
    log_dir: str,
    dry_run: bool,
    include_medium_confidence: bool = True,
    include_low_confidence: bool = False,
    limit: int | None = None,
):
    headers, rows = _read_sheet_rows(sheets_service, spreadsheet_id)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    plan_path = Path(log_dir) / f"bulk_prepare_safe_plan_{timestamp}.csv"
    plan_rows = []
    updates = []
    total_rows = 0
    filled_count = 0
    approve_count = 0
    needs_review_count = 0
    unchanged_count = 0
    reasons = Counter()
    destination_counts = Counter()
    review_column = None
    destination_column = None
    if headers and "review_decision" in headers:
        review_column = _column_letter(headers.index("review_decision"))
    if headers and "final_destination" in headers:
        destination_column = _column_letter(headers.index("final_destination"))

    safe_seen = 0
    for row in rows:
        total_rows += 1
        current_final = row.get("final_destination", "").strip()
        current_review = row.get("review_decision", "").strip()
        planned_final, destination_reason = _planned_destination_for_bulk(row)
        if not current_final and planned_final:
            filled_count += 1
            destination_counts[planned_final] += 1
        safe, approval_reason = _safe_to_approve_bulk(row, planned_final, include_medium_confidence, include_low_confidence)
        planned_review = current_review
        reason = destination_reason
        if safe and (limit is None or safe_seen < limit):
            planned_review = "APPROVE_MOVE"
            approve_count += 1
            safe_seen += 1
            if current_review == "APPROVE_MOVE" and current_final == planned_final:
                unchanged_count += 1
            elif not dry_run:
                updates.append((row["_row_number"], planned_final, planned_review))
        else:
            if current_review != "NEEDS_REVIEW":
                planned_review = "NEEDS_REVIEW"
                if not dry_run:
                    updates.append((row["_row_number"], planned_final, planned_review))
            needs_review_count += 1
            reason = approval_reason if not safe else "max limit reached"
        if current_final and current_final == planned_final and current_review == planned_review:
            unchanged_count += 1
        if not planned_final:
            reason = approval_reason if not safe else destination_reason
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
                "final_destination_planned": planned_final,
                "review_decision_current": current_review,
                "review_decision_planned": planned_review,
                "reason": reason,
            }
        )
        reasons[reason] += 1
    _write_bulk_plan_csv(plan_path, plan_rows)
    if not dry_run:
        for row_number, destination, review_decision in updates:
            if destination_column:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Sheet1!{destination_column}{row_number}",
                    valueInputOption="RAW",
                    body={"values": [[destination]]},
                ).execute()
            if review_column:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Sheet1!{review_column}{row_number}",
                    valueInputOption="RAW",
                    body={"values": [[review_decision]]},
                ).execute()
    return {
        "total_rows": total_rows,
        "filled_count": filled_count,
        "approve_count": approve_count,
        "needs_review_count": needs_review_count,
        "unchanged_count": unchanged_count,
        "top_destinations": destination_counts.most_common(5),
        "top_reasons": reasons.most_common(5),
        "plan_path": plan_path,
        "updated_rows": len(updates),
    }
