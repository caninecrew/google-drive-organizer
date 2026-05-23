from __future__ import annotations

from src.classifier import classify_file
from src.drive_activity import enrich_activity
from src.move_approved import move_approved_rows


def test_classifier_role_matching():
    role, sensitivity, destination, confidence = classify_file("TTU transcript.pdf", "application/pdf")
    assert role == "School and Education"
    assert destination == "02 School and Education"
    assert sensitivity == "School Record"
    assert confidence == "High"


def test_classifier_sensitivity_detection():
    role, sensitivity, destination, confidence = classify_file("social security card scan.png", "image/png")
    assert role == "Photos and Media"
    assert sensitivity == "Needs Sensitive Review"
    assert destination == "08 Photos and Media"
    assert confidence == "High"


def test_resume_still_goes_to_work():
    role, sensitivity, destination, confidence = classify_file(
        "resume_final.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert role == "Work and Career"
    assert destination == "03 Work and Career"
    assert confidence == "High"


def test_foia_still_goes_to_foia():
    role, sensitivity, destination, confidence = classify_file("FOIA request response letter.pdf", "application/pdf")
    assert role == "FOIA and Public Records"
    assert destination == "06 FOIA and Public Records"
    assert confidence == "High"


def test_minecraft_goofy_file_goes_to_archive_or_review_later():
    role, sensitivity, destination, confidence = classify_file("minecraft world build 1.zip", "application/zip")
    assert role == "Archive"
    assert destination in {
        "09 Archive/Childhood and Old Personal Files",
        "09 Archive/Old Random Files",
        "09 Archive/Old Games and Creative Projects",
    }
    assert confidence == "Low"


def test_no_file_marked_for_deletion_automatically():
    role, sensitivity, destination, confidence = classify_file("random old joke.txt", "text/plain")
    assert "Delete" not in destination
    assert role in {"Archive", "Review Later"}
    assert confidence == "Low"


def test_move_requires_exact_approve_move():
    drive = FakeDriveService(
        files={
            "file-1": {"id": "file-1", "name": "doc.txt", "mimeType": "text/plain", "parents": ["parent-1"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE",
                "suggested_destination": "01 Personal",
            }
        ]
    )
    results = move_approved_rows(drive, sheets, "sheet-1", False, False, True, "data/logs")
    assert results == []
    assert drive.update_calls == []


def test_blank_destination_is_skipped():
    drive = FakeDriveService(
        files={
            "file-1": {"id": "file-1", "name": "doc.txt", "mimeType": "text/plain", "parents": ["parent-1"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE_MOVE",
                "suggested_destination": "",
                "final_destination": "",
            }
        ]
    )
    results = move_approved_rows(drive, sheets, "sheet-1", False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "missing destination")]
    assert drive.update_calls == []


def test_drive_activity_missing_fields_returns_unknown():
    service = FakeActivityService(response={"activities": [{"actions": [{"detail": {"edit": {}}}]}]})
    result = enrich_activity(service, "file-1")
    assert result == {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}


class FakeDriveFiles:
    def __init__(self, drive):
        self.drive = drive

    def get(self, fileId, fields):
        return FakeExecute(self.drive._files[fileId])

    def update(self, **kwargs):
        self.drive.update_calls.append(kwargs)
        return FakeExecute({"id": kwargs["fileId"]})


class FakeDriveService:
    def __init__(self, files):
        self._files = files
        self.update_calls = []

    def files(self):
        return FakeDriveFiles(self)


class FakeSheetsValues:
    def __init__(self, rows):
        self.rows = rows

    def get(self, spreadsheetId, range):
        headers = list(self.rows[0].keys()) if self.rows else []
        values = [headers] + [[row.get(header, "") for header in headers] for row in self.rows]
        return FakeExecute({"values": values})


class FakeSheetsSpreadsheet:
    def __init__(self, rows):
        self._rows = rows

    def values(self):
        return FakeSheetsValues(self._rows)


class FakeSheetsService:
    def __init__(self, rows):
        self._rows = rows

    def spreadsheets(self):
        return FakeSheetsSpreadsheet(self._rows)


class FakeActivityQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeActivityResource:
    def __init__(self, response):
        self.response = response

    def query(self, body):
        return FakeActivityQuery(self.response)


class FakeActivityService:
    def __init__(self, response):
        self._response = response

    def activity(self):
        return FakeActivityResource(self._response)


class FakeExecute:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response
