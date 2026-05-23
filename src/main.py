from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from .auth import get_credentials, get_drive_activity_service, get_drive_service, get_sheets_service
from .auto_approve import auto_approve_safe, bulk_prepare_safe, fill_destinations
from .config import load_config
from .drive_inventory import inventory_files
from .folder_setup import FOLDER_PATHS, ensure_folder_path
from .move_approved import log_inventory_action, move_approved_rows
from .sheets_review import create_review_spreadsheet
from .summary import find_latest_inventory_csv, format_summary, load_inventory_rows, summarize_rows, write_summary_export


def cmd_inventory(args):
    config = load_config()
    creds = get_credentials()
    drive = get_drive_service(creds)
    sheets = get_sheets_service(creds)
    activity = get_drive_activity_service(creds) if config.activity_enrichment else None
    log_path = Path(config.log_dir) / f"inventory_log_{datetime.now().strftime('%Y-%m-%d')}.csv"
    rows = inventory_files(
        drive,
        activity,
        include_folders=config.include_folders,
        activity_enrichment=config.activity_enrichment,
        media_policy=config.media_policy,
    )
    spreadsheet_id, title = create_review_spreadsheet(sheets, config.review_spreadsheet_prefix, rows)
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"inventory_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    with export_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = [
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
        writer.writerow(header)
        for row in rows:
            writer.writerow([getattr(row, column) for column in header])
    log_inventory_action(log_path, "inventory", "success", f"Created spreadsheet {spreadsheet_id}")
    print(f"Created review spreadsheet: {title} ({spreadsheet_id})")
    print(f"Inventory CSV exported to: {export_path}")
    print("Inventory only. No files moved.")


def cmd_create_folders(args):
    config = load_config()
    creds = get_credentials()
    drive = get_drive_service(creds)
    for path in FOLDER_PATHS:
        ensure_folder_path(drive, path, True)
    print("Ensured folder structure exists.")


def cmd_move_approved(args):
    config = load_config()
    creds = get_credentials()
    drive = get_drive_service(creds)
    sheets = get_sheets_service(creds)
    results, plan_path, evaluated_count = move_approved_rows(
        drive,
        sheets,
        args.spreadsheet_id,
        config.allow_create_missing_destination_folders,
        config.allow_move_folders,
        config.allow_move_shortcuts,
        args.dry_run,
        config.log_dir,
    )
    summary = {"would_move": 0, "moved": 0, "skipped": 0, "error": 0}
    for _file_id, status, detail in results:
        if status == "would_move":
            summary["would_move"] += 1
        elif status == "moved":
            summary["moved"] += 1
        elif status in summary:
            summary[status] += 1
    print("Move summary:")
    print(f"  rows evaluated: {evaluated_count}")
    print(f"  WOULD_MOVE: {summary['would_move']}")
    print(f"  MOVED: {summary['moved']}")
    print(f"  SKIPPED: {summary['skipped']}")
    print(f"  ERROR: {summary['error']}")
    print(f"  move plan CSV: {plan_path}")


def cmd_summarize(args):
    if args.csv and args.latest:
        raise SystemExit("Choose either --csv or --latest, not both.")
    if args.latest:
        latest_csv = find_latest_inventory_csv()
        if latest_csv is None:
            raise SystemExit("No inventory CSV files found in data/exports. Run inventory first.")
        print(f"Selected latest inventory CSV: {latest_csv}")
        csv_path = latest_csv
    else:
        csv_path = Path(args.csv)
    rows = load_inventory_rows(csv_path)
    summary = summarize_rows(rows)
    print(format_summary(summary), end="")
    if args.export:
        export_path = write_summary_export(summary, args.export)
        print(f"summary export: {export_path}")


def cmd_auto_approve_safe(args):
    config = load_config()
    creds = get_credentials()
    sheets = get_sheets_service(creds)
    result = auto_approve_safe(
        sheets,
        args.spreadsheet_id,
        config.log_dir,
        args.dry_run,
        args.max_approve,
    )
    print("Auto-approval summary:")
    print(f"  total rows evaluated: {result['total_rows']}")
    print(f"  rows that would be marked APPROVE_MOVE: {result['approve_count']}")
    print(f"  rows that would be marked NEEDS_REVIEW: {result['needs_review_count']}")
    print(f"  rows left unchanged: {result['unchanged_count']}")
    print("  top skip reasons:")
    for reason, count in result["top_reasons"]:
        print(f"    {reason}: {count}")
    print(f"  plan CSV: {result['plan_path']}")


def cmd_fill_destinations(args):
    config = load_config()
    creds = get_credentials()
    sheets = get_sheets_service(creds)
    result = fill_destinations(
        sheets,
        args.spreadsheet_id,
        config.log_dir,
        args.dry_run,
    )
    print("Fill destinations summary:")
    print(f"  total rows evaluated: {result['total_rows']}")
    print(f"  rows that would get final_destination filled: {result['filled_count']}")
    print(f"  rows already had final_destination: {result['already_filled_count']}")
    print(f"  rows still blank: {result['still_blank_count']}")
    print(f"  planned update ranges: {result['planned_update_ranges']}")
    print(f"  batch calls sent: {result['batch_calls_sent']}")
    print("  top destination counts:")
    for destination, count in result["top_destinations"]:
        print(f"    {destination}: {count}")
    print("  top skip reasons:")
    for reason, count in result["top_reasons"]:
        print(f"    {reason}: {count}")
    print(f"  plan CSV: {result['plan_path']}")


def cmd_bulk_prepare_safe(args):
    config = load_config()
    creds = get_credentials()
    sheets = get_sheets_service(creds)
    result = bulk_prepare_safe(
        sheets,
        args.spreadsheet_id,
        config.log_dir,
        args.dry_run,
        include_medium_confidence=args.include_medium_confidence,
        include_low_confidence=args.include_low_confidence,
        limit=args.limit,
        shared_file_strategy=args.shared_file_strategy,
        owned_only=args.owned_only,
    )
    print("Bulk prepare summary:")
    print(f"  total rows evaluated: {result['total_rows']}")
    print(f"  rows that would get final_destination filled: {result['filled_count']}")
    if args.dry_run:
        print(f"  rows that would be marked APPROVE_MOVE: {result['approve_count']}")
        print(f"  rows that would be marked NEEDS_REVIEW: {result['needs_review_count']}")
    else:
        print(f"  rows marked APPROVE_MOVE: {result['approve_count']}")
        print(f"  rows marked NEEDS_REVIEW: {result['needs_review_count']}")
    print(f"  rows left unchanged: {result['unchanged_count']}")
    print(f"  owned_by_me TRUE count: {result['owned_true_count']}")
    print(f"  owned_by_me FALSE count: {result['owned_false_count']}")
    print(f"  rows with all move capability fields TRUE: {result['all_capable_true_count']}")
    print(f"  rows blocked only because not owned: {result['blocked_only_by_not_owned']}")
    print(f"  rows blocked by low confidence: {result['blocked_by_low_confidence']}")
    print(f"  rows blocked by sensitivity: {result['blocked_by_sensitivity']}")
    print(f"  rows planned APPROVE_MOVE: {result['approve_count']}")
    print(f"  planned update ranges: {result['planned_update_ranges']}")
    print(f"  batch calls sent: {result['batch_calls_sent']}")
    print("  top destination counts:")
    for destination, count in result["top_destinations"]:
        print(f"    {destination}: {count}")
    print("  top skip/risk reasons:")
    for reason, count in result["top_reasons"]:
        print(f"    {reason}: {count}")
    print(f"  plan CSV: {result['plan_path']}")


def build_parser():
    parser = argparse.ArgumentParser(prog="google-drive-organizer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("create-folders")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--csv")
    summarize.add_argument("--latest", action="store_true")
    summarize.add_argument("--export")
    move = sub.add_parser("move-approved")
    move.add_argument("--spreadsheet-id", required=True)
    move.add_argument("--dry-run", action="store_true")
    auto = sub.add_parser("auto-approve-safe")
    auto.add_argument("--spreadsheet-id", required=True)
    auto.add_argument("--dry-run", action="store_true")
    auto.add_argument("--max-approve", type=int)
    fill = sub.add_parser("fill-destinations")
    fill.add_argument("--spreadsheet-id", required=True)
    fill.add_argument("--dry-run", action="store_true")
    bulk = sub.add_parser("bulk-prepare-safe")
    bulk.add_argument("--spreadsheet-id", required=True)
    bulk.add_argument("--dry-run", action="store_true")
    bulk.add_argument("--include-medium-confidence", action=argparse.BooleanOptionalAction, default=True)
    bulk.add_argument("--include-low-confidence", action="store_true")
    bulk.add_argument("--limit", type=int)
    bulk.add_argument("--shared-file-strategy", choices=["skip", "allow-capable"], default="skip")
    bulk.add_argument("--owned-only", action="store_true")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "inventory":
        cmd_inventory(args)
    elif args.command == "create-folders":
        cmd_create_folders(args)
    elif args.command == "summarize":
        cmd_summarize(args)
    elif args.command == "move-approved":
        cmd_move_approved(args)
    elif args.command == "auto-approve-safe":
        cmd_auto_approve_safe(args)
    elif args.command == "fill-destinations":
        cmd_fill_destinations(args)
    elif args.command == "bulk-prepare-safe":
        cmd_bulk_prepare_safe(args)


if __name__ == "__main__":
    main()
