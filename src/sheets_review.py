from __future__ import annotations

from datetime import datetime

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
    "suggested_role",
    "suggested_sensitivity",
    "suggested_destination",
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
    return spreadsheet_id, title


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

