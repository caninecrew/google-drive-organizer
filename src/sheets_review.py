from __future__ import annotations

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
    return spreadsheet_id, title


def _make_validation_request(sheet_id: int, column_index: int, values: list[str]) -> dict:
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 10000,
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


def read_review_rows(sheets_service, spreadsheet_id: str):
    result = sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="Sheet1!A1:Z").execute()
    values = result.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for row in values[1:]:
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rows.append(item)
    return rows
