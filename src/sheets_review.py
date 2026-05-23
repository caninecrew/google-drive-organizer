from __future__ import annotations

from collections import Counter
from datetime import datetime

from .classifier import review_destination_options

REVIEW_DECISION_OPTIONS = [
    "REVIEW",
    "APPROVE_MOVE",
    "APPROVE_ARCHIVE",
    "SKIP",
    "NEEDS_REVIEW",
    "DELETE_LATER",
]

FINAL_DESTINATION_OPTIONS = review_destination_options()

HEADER_ROW = [
    "file_id",
    "name",
    "mime_type",
    "parents",
    "created_time",
    "modified_time",
    "owners",
    "size",
    "web_view_link",
    "current_path",
    "owned_by_me",
    "capabilities_can_move_item_within_drive",
    "capabilities_can_move_item_out_of_drive",
    "capabilities_can_add_my_drive_parent",
    "capabilities_can_remove_my_drive_parent",
    "is_shortcut",
    "shortcut_target_id",
    "shortcut_target_mime_type",
    "shortcut_target_resource_key",
    "suggested_role",
    "suggested_sensitivity",
    "suggested_destination",
    "suggested_confidence",
    "activity_level",
    "last_activity_time",
    "last_activity_type",
    "review_decision",
    "final_destination",
    "notes",
]


def create_review_spreadsheet(sheets_service, title_prefix: str, rows):
    title = f"{title_prefix} - {datetime.now().strftime('%Y-%m-%d')}"
    spreadsheet = sheets_service.spreadsheets().create(body={"properties": {"title": title}}, fields="spreadsheetId").execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    values = [HEADER_ROW] + [[getattr(row, field) for field in HEADER_ROW] for row in rows]
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    _apply_review_dropdown_validation(sheets_service, spreadsheet_id)
    _add_instructions_and_summary_sheets(sheets_service, spreadsheet_id, rows)
    return spreadsheet_id, title


def _make_validation_request(sheet_id: int, column_index: int, values: list[str]) -> dict:
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 100000,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": value} for value in values],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }


def _apply_review_dropdown_validation(sheets_service, spreadsheet_id: str):
    try:
        sheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = sheet["sheets"][0]["properties"]["sheetId"]
        request = {
            "requests": [
                {
                    **_make_validation_request(sheet_id, 17, REVIEW_DECISION_OPTIONS),
                },
                {
                    **_make_validation_request(sheet_id, 18, FINAL_DESTINATION_OPTIONS),
                }
            ]
        }
        sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=request).execute()
    except Exception:
        return


def _add_instructions_and_summary_sheets(sheets_service, spreadsheet_id: str, rows):
    instructions = [
        ["Google Drive Organizer Review Instructions"],
        [""],
        ["Inventory does not move files."],
        ["review_decision controls what action the tool may take."],
        ["final_destination controls where the file goes."],
        ["suggested_destination is only a recommendation."],
        ["APPROVE_MOVE only works when final_destination is filled."],
        ["Use dry-run before any real move."],
        ["Do not approve Low confidence, sensitive, shortcut, unknown-parent, or not-owned-by-me rows without manual review."],
        ["Start real moves with a tiny 5-10 file test batch."],
        ["If activity enrichment is disabled, activity_level will be Unknown."],
    ]
    summary = _build_summary_sheet(rows)
    try:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": "Instructions",
                            }
                        }
                    },
                    {
                        "addSheet": {
                            "properties": {
                                "title": "Summary",
                            }
                        }
                    },
                ]
            },
        ).execute()
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Instructions!A1",
            valueInputOption="RAW",
            body={"values": instructions},
        ).execute()
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Summary!A1",
            valueInputOption="RAW",
            body={"values": summary},
        ).execute()
    except Exception:
        return


def _build_summary_sheet(rows):
    counter_role = Counter()
    counter_destination = Counter()
    counter_confidence = Counter()
    counter_sensitivity = Counter()
    counter_activity = Counter()
    untitled_by_role = Counter()
    unknown_parent_count = 0
    shortcut_count = 0
    not_owned_count = 0
    low_confidence_count = 0
    for row in rows:
        counter_role[row.suggested_role] += 1
        counter_destination[row.suggested_destination] += 1
        counter_confidence[row.suggested_confidence] += 1
        counter_sensitivity[row.suggested_sensitivity] += 1
        counter_activity[row.activity_level] += 1
        if "Unknown Parent" in row.current_path:
            unknown_parent_count += 1
        if row.is_shortcut == "True":
            shortcut_count += 1
        if row.owned_by_me != "True":
            not_owned_count += 1
        if row.suggested_confidence == "Low":
            low_confidence_count += 1
        if "Untitled" in row.name:
            untitled_by_role[row.suggested_role] += 1
    values = [["metric", "value"]]
    values += [["total files scanned", len(rows)]]
    values += [["count of Unknown Parent rows", unknown_parent_count]]
    values += [["count of shortcut rows", shortcut_count]]
    values += [["count of not-owned-by-me rows", not_owned_count]]
    values += [["count of Low confidence rows", low_confidence_count]]
    values += [["count by suggested_role", ""]]
    values += [[k, v] for k, v in counter_role.items()]
    values += [["count by suggested_destination", ""]]
    values += [[k, v] for k, v in counter_destination.items()]
    values += [["count by suggested_confidence", ""]]
    values += [[k, v] for k, v in counter_confidence.items()]
    values += [["count by suggested_sensitivity", ""]]
    values += [[k, v] for k, v in counter_sensitivity.items()]
    values += [["count by activity_level", ""]]
    values += [[k, v] for k, v in counter_activity.items()]
    values += [["count of Untitled files by suggested_role", ""]]
    values += [[k, v] for k, v in untitled_by_role.items()]
    return values


def read_review_rows(sheets_service, spreadsheet_id: str):
    result = sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="Sheet1!A1:ZZ").execute()
    values = result.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for row in values[1:]:
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rows.append(item)
    return rows
