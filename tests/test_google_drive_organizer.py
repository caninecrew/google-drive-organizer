from __future__ import annotations

import csv
import os
from pathlib import Path

from src.auto_approve import auto_approve_safe
from src.classifier import classify_file
from src.drive_activity import enrich_activity
from src.drive_inventory import inventory_files
from src.drive_inventory import _resolve_path
from src.move_approved import move_approved_rows
from src.summary import build_warnings, find_latest_inventory_csv, format_summary, summarize_rows
from src.sheets_review import FINAL_DESTINATION_OPTIONS, REVIEW_DECISION_OPTIONS, _make_validation_request


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


def test_untitled_document_with_no_useful_path_goes_to_review_later():
    role, sensitivity, destination, confidence = classify_file("Untitled document", "application/vnd.google-apps.document")
    assert role == "Review Later"
    assert destination == "99 Review Later"
    assert confidence == "Low"


def test_untitled_document_inside_foia_path_goes_to_foia():
    role, sensitivity, destination, confidence = classify_file(
        "Untitled document",
        "application/vnd.google-apps.document",
        current_path="My Drive/FOIA/Public Records/requests/Untitled document",
    )
    assert role == "FOIA and Public Records"
    assert destination == "06 FOIA and Public Records"
    assert confidence in {"Medium", "Low"}


def test_untitled_document_inside_school_path_goes_to_school():
    role, sensitivity, destination, confidence = classify_file(
        "Untitled document",
        "application/vnd.google-apps.document",
        current_path="My Drive/Tennessee Tech/DS 4250/Untitled document",
    )
    assert role == "School and Education"
    assert destination == "02 School and Education"
    assert confidence in {"Medium", "Low"}


def test_untitled_document_not_automatically_archived():
    role, sensitivity, destination, confidence = classify_file("Untitled document", "application/vnd.google-apps.document")
    assert role != "Archive"
    assert "Archive" not in destination or destination == "99 Review Later"


def test_path_based_classification_overrides_goofy_filename():
    role, sensitivity, destination, confidence = classify_file(
        "goofy_file.txt",
        "text/plain",
        current_path="My Drive/FOIA/Public Records/requests/goofy_file.txt",
    )
    assert role == "FOIA and Public Records"
    assert destination == "06 FOIA and Public Records"
    assert confidence == "Medium"


def test_academic_and_career_path_is_mixed_context():
    role, sensitivity, destination, confidence = classify_file(
        "Chapter 17 - Cheat Sheet",
        "application/pdf",
        current_path="My Drive/Academic and Career/Accounting 2",
    )
    assert role in {"School and Education", "Review Later"}
    assert role != "Work and Career"


def test_academic_and_career_path_can_still_classify_career_files():
    role, sensitivity, destination, confidence = classify_file(
        "Resume 2026",
        "application/pdf",
        current_path="My Drive/Academic and Career/Job Search",
    )
    assert role == "Work and Career"


def test_resume_goes_to_work():
    role, sensitivity, destination, confidence = classify_file("Resume 2026.pdf", "application/pdf")
    assert role == "Work and Career"
    assert destination == "03 Work and Career"
    assert confidence == "High"


def test_gideons_onboarding_goes_to_work():
    role, sensitivity, destination, confidence = classify_file("Gideons onboarding checklist.pdf", "application/pdf")
    assert role == "Work and Career"
    assert destination == "03 Work and Career"


def test_scouting_application_not_career_when_context_supports_scouting():
    role, sensitivity, destination, confidence = classify_file(
        "MTC QD Officer Application",
        "application/pdf",
        current_path="My Drive/Scouting/Order of the Arrow/MTC QD Officer Application",
    )
    assert role == "Scouting"
    assert destination == "04 Scouting"


def test_sale_does_not_become_work():
    role, sensitivity, destination, confidence = classify_file("30% Off Sale", "text/plain")
    assert role in {"Review Later", "Photos and Media", "Archive"}
    assert role != "Work and Career"


def test_interview_needs_job_context():
    role, sensitivity, destination, confidence = classify_file("Cindy Interview", "application/pdf")
    assert role != "Work and Career"


def test_python_project_goes_to_coding():
    role, sensitivity, destination, confidence = classify_file("Python project - news sources", "application/pdf")
    assert role == "Projects and Coding"
    assert destination == "07 Projects and Coding"


def test_venturing_summit_project_not_automatically_coding():
    role, sensitivity, destination, confidence = classify_file(
        "Venturing Summit Project",
        "application/pdf",
        current_path="My Drive/Scouting/Venturing Summit Project",
    )
    assert role == "Scouting"


def test_project_word_alone_not_coding():
    role, sensitivity, destination, confidence = classify_file("23rd Amendment Project", "application/pdf")
    assert role != "Projects and Coding"


def test_untitled_file_with_no_useful_path_goes_to_review_later():
    role, sensitivity, destination, confidence = classify_file("Untitled", "text/plain", current_path="My Drive/Random/Untitled")
    assert role == "Review Later"
    assert destination == "99 Review Later"
    assert confidence == "Low"


def test_untitled_school_path_stays_school():
    role, sensitivity, destination, confidence = classify_file(
        "Untitled",
        "text/plain",
        current_path="My Drive/Tennessee Tech/DS 4250/Untitled",
    )
    assert role == "School and Education"
    assert destination == "02 School and Education"
    assert confidence == "Medium"


def test_minecraft_in_old_childhood_path_goes_to_archive_games():
    role, sensitivity, destination, confidence = classify_file(
        "minecraft save 1.zip",
        "application/zip",
        current_path="My Drive/Archive/Childhood Files/Old Games/minecraft save 1.zip",
    )
    assert role == "Archive"
    assert destination == "09 Archive/Old Games and Creative Projects"
    assert confidence == "High"


def test_course_syllabus_normal_sensitivity():
    role, sensitivity, destination, confidence = classify_file("Course Syllabus", "application/pdf")
    assert sensitivity == "Normal"


def test_university_of_scouting_syllabus_normal_sensitivity():
    role, sensitivity, destination, confidence = classify_file("University of Scouting syllabus", "application/pdf")
    assert sensitivity == "Normal"


def test_tn_tech_class_schedule_can_be_student_information():
    role, sensitivity, destination, confidence = classify_file("TN Tech Class Schedule", "application/pdf", current_path="My Drive/Tennessee Tech/Spring 2026")
    assert sensitivity in {"Student Information", "School Record", "Normal"}


def test_incident_report_sensitive():
    role, sensitivity, destination, confidence = classify_file("Incident Report", "application/pdf")
    assert sensitivity in {"Needs Sensitive Review", "Student Information"}


def test_code_of_conduct_is_not_automatically_sensitive():
    role, sensitivity, destination, confidence = classify_file("Personal Code of Conduct", "application/pdf")
    assert sensitivity == "Normal"


def test_linus_slow_motion_fall_is_normal():
    role, sensitivity, destination, confidence = classify_file("Linus Slow Motion Fall.mp4", "video/mp4")
    assert sensitivity == "Normal"


def test_transcript_of_public_statement_not_school_record():
    role, sensitivity, destination, confidence = classify_file("Transcript of Iskall's public statement 2025-01-30", "application/pdf")
    assert sensitivity != "School Record"


def test_academic_transcripts_still_school_record():
    role, sensitivity, destination, confidence = classify_file("Rumbley-TN Tech Transcript.pdf", "application/pdf")
    assert sensitivity == "School Record"


def test_wilson_bank_and_trust_sponsor_letter_not_financial_by_default():
    role, sensitivity, destination, confidence = classify_file("Letter to Sponsor (Wilson Bank and Trust)", "application/pdf")
    assert sensitivity in {"Normal", "Needs Sensitive Review", "Legal/Public Records"}


def test_phase_10_score_sheet_not_automatically_coding():
    role, sensitivity, destination, confidence = classify_file("Phase 10 Score Sheet", "application/pdf")
    assert role in {"Review Later", "Personal", "Archive"}


def test_phase_10_development_context_can_be_coding():
    role, sensitivity, destination, confidence = classify_file(
        "Phase 10 implementation notes",
        "application/pdf",
        current_path="My Drive/Projects/Python",
    )
    assert role == "Projects and Coding"


def test_family_history_videos_get_personal_family_history_destination():
    role, sensitivity, destination, confidence = classify_file(
        "Family History Videos",
        "video/mp4",
    )
    assert destination in {
        "01 Personal/Family History/Video Interviews",
        "08 Photos and Media/Family History Videos",
    }


def test_word_bank_does_not_become_financial():
    role, sensitivity, destination, confidence = classify_file("L2 - word bank", "application/pdf")
    assert sensitivity != "Financial"


def test_fall_video_not_student_information():
    role, sensitivity, destination, confidence = classify_file("Linus Slow Motion Fall.mp4", "video/mp4")
    assert sensitivity == "Normal"


def test_media_policy_role_first_keeps_scouting_media_in_scouting():
    role, sensitivity, destination, confidence = classify_file(
        "Camp photo.jpg",
        "image/jpeg",
        current_path="My Drive/Scouting/Boxwell",
        media_policy="role_first",
    )
    assert role == "Scouting"
    assert destination in {"04 Scouting", "04 Scouting/Photos"}


def test_media_policy_media_first_routes_scouting_media_to_photos():
    role, sensitivity, destination, confidence = classify_file(
        "Camp photo.jpg",
        "image/jpeg",
        current_path="My Drive/Scouting/Boxwell",
        media_policy="media_first",
    )
    assert destination == "08 Photos and Media/Scouting Photos"


def test_inventory_metadata_includes_owner_and_shortcut_fields():
    drive = FakeDriveService(
        files={
            "folder-1": {"id": "folder-1", "name": "Docs", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
            "shortcut-1": {
                "id": "shortcut-1",
                "name": "Shortcut to Doc",
                "mimeType": "application/vnd.google-apps.shortcut",
                "parents": ["folder-1"],
                "createdTime": "2026-01-01T00:00:00Z",
                "modifiedTime": "2026-01-02T00:00:00Z",
                "owners": [{"displayName": "Sam"}],
                "webViewLink": "https://example.com",
                "ownedByMe": False,
                "capabilities": {
                    "canMoveItemWithinDrive": False,
                    "canMoveItemOutOfDrive": False,
                    "canAddMyDriveParent": False,
                    "canRemoveMyDriveParent": False,
                },
                "shortcutDetails": {
                    "targetId": "target-1",
                    "targetMimeType": "application/pdf",
                    "targetResourceKey": "rk-1",
                },
            },
        }
    )
    rows = inventory_files(drive, include_folders=False, activity_enrichment=False)
    shortcut_row = next(row for row in rows if row.file_id == "shortcut-1")
    assert shortcut_row.owned_by_me == "False"
    assert shortcut_row.capabilities_can_move_item_within_drive == "False"
    assert shortcut_row.is_shortcut == "True"
    assert shortcut_row.shortcut_target_id == "target-1"
    assert shortcut_row.shortcut_target_mime_type == "application/pdf"
    assert shortcut_row.shortcut_target_resource_key == "rk-1"


def test_path_builder_handles_missing_parent_safely():
    current_path, note = _resolve_path({"name": "notes.docx", "parents": ["missing-parent"]}, folder_cache={})
    assert current_path == "Unknown Parent/notes.docx"
    assert note


def test_path_builder_fetches_missing_parent_from_drive():
    drive = FakeDriveService(
        files={
            "folder-2": {"id": "folder-2", "name": "Tennessee Tech", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
            "folder-1": {"id": "folder-1", "name": "DS 4250", "mimeType": "application/vnd.google-apps.folder", "parents": ["folder-2"]},
        }
    )
    current_path, note = _resolve_path({"name": "notes.docx", "parents": ["folder-1"]}, folder_cache={}, drive_service=drive)
    assert current_path == "My Drive/Tennessee Tech/DS 4250/notes.docx"
    assert note == ""


def test_path_builder_resolves_readable_path_order():
    folder_cache = {
        "folder-1": {"name": "DS 4250", "parent": "folder-2"},
        "folder-2": {"name": "Tennessee Tech", "parent": "root"},
    }
    current_path, note = _resolve_path({"name": "notes.docx", "parents": ["folder-1"]}, folder_cache=folder_cache)
    assert current_path == "My Drive/Tennessee Tech/DS 4250/notes.docx"
    assert note == ""


def test_path_builder_normalizes_duplicate_my_drive_prefix():
    drive = FakeDriveService(
        files={
            "folder-2": {"id": "folder-2", "name": "My Drive", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
            "folder-1": {"id": "folder-1", "name": "Folder", "mimeType": "application/vnd.google-apps.folder", "parents": ["folder-2"]},
        }
    )
    current_path, note = _resolve_path({"name": "File", "parents": ["folder-1"]}, folder_cache={}, drive_service=drive)
    assert current_path == "My Drive/Folder/File"
    assert note == ""


def test_path_builder_keeps_unknown_parent_prefix():
    current_path, note = _resolve_path({"name": "File", "parents": []}, folder_cache={})
    assert current_path == "Unknown Parent/File"
    assert note == "no parents"


def test_move_requires_exact_approve_move():
    drive = FakeDriveService(
        files={
            "file-1": {"id": "file-1", "name": "doc.txt", "mimeType": "text/plain", "parents": ["parent-1"]},
            "02-school": {"id": "02-school", "name": "02 School and Education", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
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
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "review_decision is not APPROVE_MOVE")]
    assert drive.update_calls == []
    assert evaluated_count == 1
    assert plan_path.exists()
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["outcome"] == "SKIPPED"
    assert rows[0]["reason"] == "review_decision is not APPROVE_MOVE"
    assert rows[0]["current_path"] == ""


def test_blank_destination_is_skipped():
    drive = FakeDriveService(
        files={
            "file-1": {"id": "file-1", "name": "doc.txt", "mimeType": "text/plain", "parents": ["parent-1"]},
            "02-school": {"id": "02-school", "name": "02 School and Education", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
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
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "final destination is blank")]
    assert drive.update_calls == []
    assert evaluated_count == 1
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["outcome"] == "SKIPPED"
    assert rows[0]["reason"] == "final destination is blank"


def test_approve_move_with_blank_final_destination_is_skipped():
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
                "suggested_destination": "01 Personal",
                "final_destination": "",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "final destination is blank")]
    assert drive.update_calls == []
    assert evaluated_count == 1
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["outcome"] == "SKIPPED"
    assert rows[0]["reason"] == "final destination is blank"


def test_dry_run_produces_would_move_without_update_call():
    drive = FakeDriveService(
        files={
            "file-1": {"id": "file-1", "name": "doc.txt", "mimeType": "text/plain", "parents": ["parent-1"]},
            "02-school": {"id": "02-school", "name": "02 School and Education", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
            "dest-1": {"id": "dest-1", "name": "01 Personal", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE_MOVE",
                "suggested_destination": "01 Personal",
                "final_destination": "02 School and Education",
                "current_path": "My Drive/Docs/doc.txt",
                "parents": "parent-1",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "would_move", "02 School and Education")]
    assert drive.update_calls == []
    assert evaluated_count == 1
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["outcome"] == "WOULD_MOVE"
    assert rows[0]["current_path"] == "My Drive/Docs/doc.txt"
    assert rows[0]["destination_path"] == "02 School and Education"


def test_move_approved_uses_final_destination_not_suggested_destination():
    drive = FakeDriveService(
        files={
            "file-1": {
                "id": "file-1",
                "name": "doc.txt",
                "mimeType": "text/plain",
                "parents": ["parent-1"],
                "ownedByMe": True,
                "capabilities": {
                    "canMoveItemWithinDrive": True,
                    "canMoveItemOutOfDrive": True,
                    "canAddMyDriveParent": True,
                    "canRemoveMyDriveParent": True,
                },
            },
            "dest-1": {"id": "dest-1", "name": "02 School and Education", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE_MOVE",
                "suggested_destination": "01 Personal",
                "final_destination": "02 School and Education",
                "current_path": "My Drive/Docs/doc.txt",
                "parents": "parent-1",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "would_move", "02 School and Education")]
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["destination_path"] == "02 School and Education"


def test_shortcut_rows_are_skipped_by_default():
    drive = FakeDriveService(
        files={
            "file-1": {
                "id": "file-1",
                "name": "shortcut",
                "mimeType": "application/vnd.google-apps.shortcut",
                "parents": ["parent-1"],
                "ownedByMe": True,
                "capabilities": {
                    "canMoveItemWithinDrive": True,
                    "canMoveItemOutOfDrive": True,
                    "canAddMyDriveParent": True,
                    "canRemoveMyDriveParent": True,
                },
            },
            "01-personal": {"id": "01-personal", "name": "01 Personal", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "shortcut",
                "review_decision": "APPROVE_MOVE",
                "final_destination": "01 Personal",
                "current_path": "My Drive/Docs/shortcut",
                "parents": "parent-1",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "shortcut moves disabled")]
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["reason"] == "shortcut moves disabled"


def test_not_owned_file_without_capability_is_skipped():
    drive = FakeDriveService(
        files={
            "file-1": {
                "id": "file-1",
                "name": "doc.txt",
                "mimeType": "text/plain",
                "parents": ["parent-1"],
                "ownedByMe": False,
                "capabilities": {
                    "canMoveItemWithinDrive": False,
                    "canMoveItemOutOfDrive": False,
                    "canAddMyDriveParent": True,
                    "canRemoveMyDriveParent": True,
                },
            },
            "01-personal": {"id": "01-personal", "name": "01 Personal", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE_MOVE",
                "final_destination": "01 Personal",
                "current_path": "My Drive/Docs/doc.txt",
                "parents": "parent-1",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "file not owned by authenticated user")]
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["reason"] == "file not owned by authenticated user"


def test_not_movable_file_is_skipped_when_capabilities_missing():
    drive = FakeDriveService(
        files={
            "file-1": {
                "id": "file-1",
                "name": "doc.txt",
                "mimeType": "text/plain",
                "parents": ["parent-1"],
                "ownedByMe": True,
                "capabilities": {
                    "canMoveItemWithinDrive": False,
                    "canMoveItemOutOfDrive": False,
                    "canAddMyDriveParent": False,
                    "canRemoveMyDriveParent": False,
                },
            },
            "01-personal": {"id": "01-personal", "name": "01 Personal", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        }
    )
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "doc.txt",
                "review_decision": "APPROVE_MOVE",
                "final_destination": "01 Personal",
                "current_path": "My Drive/Docs/doc.txt",
                "parents": "parent-1",
            }
        ]
    )
    results, plan_path, evaluated_count = move_approved_rows(drive, sheets, "sheet-1", False, False, False, True, "data/logs")
    assert results == [("file-1", "skipped", "cannot add destination parent")]
    with plan_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["reason"] == "cannot add destination parent"


def test_drive_activity_missing_fields_returns_unknown():
    service = FakeActivityService(response={"activities": [{"actions": [{"detail": {"edit": {}}}]}]})
    result = enrich_activity(service, "file-1")
    assert result == {"activity_level": "Unknown", "last_activity_time": "", "last_activity_type": ""}


def test_summary_helpers_count_rows_and_warnings():
    rows = [
        {
            "suggested_role": "Work and Career",
            "suggested_destination": "03 Work and Career",
            "suggested_confidence": "Low",
            "suggested_sensitivity": "Normal",
            "current_path": "Unknown Parent/file1 [unresolved parent]",
            "name": "Untitled document",
            "review_decision": "APPROVE_MOVE",
        },
        {
            "suggested_role": "Review Later",
            "suggested_destination": "99 Review Later",
            "suggested_confidence": "Low",
            "suggested_sensitivity": "Normal",
            "current_path": "My Drive/School/file2",
            "name": "Resume 2026",
            "review_decision": "",
        },
    ]
    summary = summarize_rows(rows)
    assert summary.total_rows == 2
    assert summary.by_role["Work and Career"] == 1
    assert summary.by_confidence["Low"] == 2
    assert summary.untitled_count == 1
    assert summary.low_confidence_approve_move_count == 1
    assert "More than 10% of rows are Work and Career." in summary.warnings
    assert "Some Low confidence rows are marked APPROVE_MOVE." in summary.warnings
    text = format_summary(summary)
    assert "total rows: 2" in text


def test_summary_build_warnings_thresholds():
    warnings = build_warnings(
        total_rows=10,
        unknown_parent_count=3,
        work_and_career_count=2,
        untitled_count=5,
        untitled_archive_count=1,
        low_confidence_approve_move_count=0,
    )
    assert "More than 25% of rows have Unknown Parent." in warnings
    assert "More than 10% of rows are Work and Career." in warnings


def test_review_decision_dropdown_values_do_not_include_folder_paths():
    assert "APPROVE_MOVE" in REVIEW_DECISION_OPTIONS
    assert all(not value.startswith("0") for value in REVIEW_DECISION_OPTIONS)


def test_final_destination_dropdown_values_include_folder_paths():
    assert "01 Personal" in FINAL_DESTINATION_OPTIONS
    assert "09 Archive/Old Games and Creative Projects" in FINAL_DESTINATION_OPTIONS


def test_validation_request_targets_correct_columns():
    review_req = _make_validation_request(1, 17, REVIEW_DECISION_OPTIONS)
    final_req = _make_validation_request(1, 18, FINAL_DESTINATION_OPTIONS)
    assert review_req["setDataValidation"]["range"]["startColumnIndex"] == 17
    assert review_req["setDataValidation"]["range"]["endColumnIndex"] == 18
    assert final_req["setDataValidation"]["range"]["startColumnIndex"] == 18
    assert final_req["setDataValidation"]["range"]["endColumnIndex"] == 19
    assert review_req["setDataValidation"]["range"]["endRowIndex"] >= 100000
    assert final_req["setDataValidation"]["range"]["endRowIndex"] >= 100000


def test_find_latest_inventory_csv_selects_newest(tmp_path):
    older = tmp_path / "inventory_2026-01-01_120000.csv"
    newer = tmp_path / "inventory_2026-01-02_120000.csv"
    older.write_text("a,b\n1,2\n", encoding="utf-8")
    newer.write_text("a,b\n3,4\n", encoding="utf-8")
    os.utime(older, (older.stat().st_atime, older.stat().st_mtime - 10))
    assert find_latest_inventory_csv(tmp_path) == newer


def test_find_latest_inventory_csv_returns_none_when_missing(tmp_path):
    assert find_latest_inventory_csv(tmp_path) is None


def test_summary_csv_conflict_error(tmp_path):
    from src.main import cmd_summarize

    csv_path = tmp_path / "inventory_2026-01-01_120000.csv"
    csv_path.write_text("suggested_role\nReview Later\n", encoding="utf-8")

    class Args:
        csv = str(csv_path)
        latest = True
        export = None

    try:
        cmd_summarize(Args())
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "Choose either --csv or --latest" in str(exc)


def test_existing_csv_behavior_still_works(tmp_path, capsys):
    from src.main import cmd_summarize

    csv_path = tmp_path / "inventory_2026-01-01_120000.csv"
    csv_path.write_text(
        "suggested_role,suggested_destination,suggested_confidence,suggested_sensitivity,current_path,name,review_decision\n"
        "Review Later,99 Review Later,Low,Normal,My Drive/Test,Untitled,\n",
        encoding="utf-8",
    )

    class Args:
        csv = str(csv_path)
        latest = False
        export = None

    cmd_summarize(Args())
    captured = capsys.readouterr()
    assert "total rows: 1" in captured.out


def test_safe_row_becomes_planned_approve_move(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-1",
                "name": "Resume 2026",
                "current_path": "My Drive/Work/Resume 2026",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
                "capabilities_can_move_item_within_drive": "True",
                "capabilities_can_add_my_drive_parent": "True",
                "capabilities_can_remove_my_drive_parent": "True",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    assert result["approve_count"] == 1
    assert result["needs_review_count"] == 0
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "APPROVE_MOVE"


def test_low_confidence_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-2",
                "name": "random note",
                "current_path": "My Drive/Random/random note",
                "suggested_role": "Review Later",
                "suggested_confidence": "Low",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "99 Review Later",
                "review_decision": "REVIEW",
                "mime_type": "text/plain",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    assert result["needs_review_count"] == 1
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "low confidence"


def test_sensitive_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-3",
                "name": "tax return",
                "current_path": "My Drive/Tax/tax return",
                "suggested_role": "Personal",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Financial",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "01 Personal",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "non-normal sensitivity"


def test_shortcut_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-4",
                "name": "shortcut",
                "current_path": "My Drive/Docs/shortcut",
                "suggested_role": "Scouting",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "True",
                "final_destination": "04 Scouting",
                "review_decision": "REVIEW",
                "mime_type": "application/vnd.google-apps.shortcut",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "shortcut"


def test_not_owned_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-5",
                "name": "doc.txt",
                "current_path": "My Drive/Docs/doc.txt",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "False",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "text/plain",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "not owned by me"


def test_unknown_parent_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-6",
                "name": "doc.txt",
                "current_path": "Unknown Parent/doc.txt [no parents]",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "text/plain",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "unknown parent"


def test_untitled_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-7",
                "name": "Untitled document",
                "current_path": "My Drive/Docs/Untitled document",
                "suggested_role": "Review Later",
                "suggested_confidence": "Low",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "99 Review Later",
                "review_decision": "REVIEW",
                "mime_type": "application/vnd.google-apps.document",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "low confidence"


def test_blank_final_destination_row_becomes_needs_review(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-8",
                "name": "doc.txt",
                "current_path": "My Drive/Docs/doc.txt",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "",
                "review_decision": "REVIEW",
                "mime_type": "text/plain",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    with result["plan_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["planned_review_decision"] == "NEEDS_REVIEW"
    assert rows[0]["reason"] == "blank final_destination"


def test_dry_run_does_not_write_to_sheets(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-9",
                "name": "Resume 2026",
                "current_path": "My Drive/Work/Resume 2026",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
            }
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), True, None)
    assert sheets.update_calls == []


def test_max_approve_limits_approvals(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-10",
                "name": "Resume 1",
                "current_path": "My Drive/Work/Resume 1",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
            },
            {
                "file_id": "file-11",
                "name": "Resume 2",
                "current_path": "My Drive/Work/Resume 2",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
            },
        ]
    )
    result = auto_approve_safe(sheets, "sheet-1", str(tmp_path), False, 1)
    assert result["approve_count"] == 1
    assert result["updated_rows"] == 1
    assert sheets.update_calls[0]["range"].startswith("Sheet1!")
    assert sheets.update_calls[0]["body"]["values"][0][0] == "APPROVE_MOVE"


def test_auto_approve_never_changes_final_destination(tmp_path):
    sheets = FakeSheetsService(
        rows=[
            {
                "file_id": "file-12",
                "name": "Resume 2026",
                "current_path": "My Drive/Work/Resume 2026",
                "suggested_role": "Work and Career",
                "suggested_confidence": "High",
                "suggested_sensitivity": "Normal",
                "owned_by_me": "True",
                "is_shortcut": "False",
                "final_destination": "03 Work and Career",
                "review_decision": "REVIEW",
                "mime_type": "application/pdf",
            }
        ]
    )
    auto_approve_safe(sheets, "sheet-1", str(tmp_path), False, None)
    assert all("final_destination" not in call["range"] for call in sheets.update_calls)


class FakeDriveFiles:
    def __init__(self, drive):
        self.drive = drive

    def get(self, fileId, fields):
        return FakeExecute(self.drive._files[fileId])

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        files = []
        if "mimeType = 'application/vnd.google-apps.folder'" in query:
            for file in self.drive._files.values():
                if file.get("mimeType") == "application/vnd.google-apps.folder":
                    files.append(file)
        else:
            for file in self.drive._files.values():
                if file.get("mimeType") != "application/vnd.google-apps.folder":
                    files.append(file)
        return FakeExecute({"files": files})

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
    def __init__(self, rows, service=None):
        self.rows = rows
        self.service = service

    def get(self, spreadsheetId, range):
        headers = list(self.rows[0].keys()) if self.rows else []
        values = [headers] + [[row.get(header, "") for header in headers] for row in self.rows]
        return FakeExecute({"values": values})

    def update(self, spreadsheetId, range, valueInputOption, body):
        if self.service is not None:
            self.service.update_calls.append({"spreadsheetId": spreadsheetId, "range": range, "valueInputOption": valueInputOption, "body": body})
        return FakeExecute({"updatedRange": range, "body": body})


class FakeSheetsSpreadsheet:
    def __init__(self, rows, service=None):
        self._rows = rows
        self._service = service

    def values(self):
        return FakeSheetsValues(self._rows, service=self._service)


class FakeSheetsService:
    def __init__(self, rows):
        self._rows = rows
        self.update_calls = []

    def spreadsheets(self):
        return FakeSheetsSpreadsheet(self._rows, service=self)


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
