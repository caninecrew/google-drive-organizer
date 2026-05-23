# google-drive-organizer

Safe Google Drive organization assistant for personal use.

## What it does

- Inventories non-trashed files from My Drive.
- Writes review rows to Google Sheets.
- Suggests categories, destination folders, sensitivity, and activity metadata.
- Includes a readable `current_path` column so folder context can influence review decisions.
- Includes owner, capability, and shortcut metadata so risky rows can be reviewed safely.
- Moves only files that you explicitly approve in the review sheet.
- Never deletes files.

## Windows PowerShell Setup

```powershell
cd "C:\Users\Samue\OneDrive\Documents\google-drive-organizer"
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest
python -m src.main inventory
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Setup

1. Create a Google Cloud project.
2. Enable:
   - Google Drive API
   - Google Sheets API
   - Drive Activity API
3. Create OAuth desktop app credentials.
4. Download the OAuth file as `credentials.json` into the project root.
5. Create a virtual environment.
6. Install dependencies:

```bash
pip install -r requirements.txt
```

## Authentication

The app uses a local desktop OAuth flow and stores the token in `token.json`.

Required scopes:

- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/drive.activity.readonly`

## Commands

Inventory only:

```bash
python -m src.main inventory
```

Create the destination folder structure:

```bash
python -m src.main create-folders
```

Move approved rows from a review spreadsheet, with a dry run first:

```bash
python -m src.main move-approved --spreadsheet-id SPREADSHEET_ID --dry-run
```

Every `move-approved` run writes a move plan CSV under `data/logs/` with the proposed or completed actions, including `current_path`, destination, and reason codes for skipped rows.

The review workbook includes three sheets:

- `Sheet1` for the inventory rows.
- `Instructions` for the review rules.
- `Summary` for counts and quality checks.

In the review sheet:

- `review_decision` controls what action the tool may take.
- `final_destination` controls where the file should go.
- `suggested_destination` is only the tool's recommendation.
- `APPROVE_MOVE` should only be used after `final_destination` is verified.
- `review_decision` options are action/status values only.
- `final_destination` options are folder paths only.
- Owner and capability columns show whether a file is owned by you and whether Drive says it can be moved safely.
- Shortcut rows are flagged explicitly. Moving a shortcut moves the shortcut entry, not necessarily the underlying target file.
- `activity_level` stays `Unknown` when activity enrichment is disabled in config.

Safe bulk approval workflow:

```bash
python -m src.main auto-approve-safe --spreadsheet-id SPREADSHEET_ID --dry-run --max-approve 10
python -m src.main auto-approve-safe --spreadsheet-id SPREADSHEET_ID --max-approve 10
python -m src.main move-approved --spreadsheet-id SPREADSHEET_ID --dry-run
```

Recommended steps:

1. Run inventory.
2. Review the summary.
3. Run `auto-approve-safe` with `--dry-run --max-approve 10`.
4. Run `auto-approve-safe` with `--max-approve 10`.
5. Run `move-approved --dry-run`.
6. Review the move plan CSV.
7. Run a real move only for that tiny approved batch.
8. Increase the batch size gradually after reviewing each pass.

Summarize an exported inventory CSV before moving:

```bash
python -m src.main summarize --csv data/exports/inventory_YYYY-MM-DD_HHMMSS.csv
```

Summarize the newest inventory CSV automatically:

```bash
python -m src.main summarize --latest
```

Export the summary to a text or CSV file:

```bash
python -m src.main summarize --csv data/exports/inventory_YYYY-MM-DD_HHMMSS.csv --export data/logs/inventory_summary.txt
```

You can combine `--latest` with `--export`:

```bash
python -m src.main summarize --latest --export data/exports/summary_latest.txt
```

Use either `--latest` or `--csv`, not both. The command will return a clear error if both are provided.

## Review workflow

1. Run inventory.
2. Run the summary command.
3. Create or refresh the destination folder structure.
4. Open the generated spreadsheet.
5. Review suggestions and set `review_decision` to `APPROVE_MOVE` only for rows you want moved.
6. Fill in `final_destination` for each approved row.
7. Start with only 5 to 10 obvious rows.
8. Run `move-approved` with `--dry-run` first.
9. Review the generated move plan CSV before making any real changes.
10. Run `move-approved` without `--dry-run` only after confirming the dry run output.
11. Review the inventory summary for unresolved parents, low-confidence rows, shortcuts, and untitled files before approving moves.

## Why `current_path` matters

- Classification now uses both filename and folder path.
- A goofy or untitled filename inside a school, FOIA, work, or scouting folder may still be serious.
- `current_path` helps review old, ambiguous, or inherited files without forcing them into archive buckets too early.
- `Untitled` usually means manual review unless the folder path gives clear context.
- `Project` alone does not mean coding, and `Application` alone does not mean career.
- `Academic and Career` is treated as mixed context, so the folder path alone does not force Work and Career.
- `transcript` only means School Record in an academic-record context.
- `bank` only means Financial when there is actual financial/account/tax/payment context.
- Phase 10 score sheets are not automatically coding projects.
- Low-confidence rows should be reviewed manually before any move is approved.
- `Instructions` and `Summary` sheets are included so you can review the workbook without reading the code.

## Media Policy

The default `media_policy` is `role_first`.

- `role_first` keeps Scouting media in Scouting, Church media in Church and Ministry, and family-history media in the personal family-history folders when possible.
- `media_first` prioritizes the media buckets under `08 Photos and Media`.
- Scouting photos can go to `04 Scouting/Photos` or `08 Photos and Media/Scouting Photos` depending on `media_policy`.
- Family history videos can go to `01 Personal/Family History/Video Interviews` or `08 Photos and Media/Family History Videos` depending on `media_policy`.

## First Real Run Checklist

1. Verify `credentials.json` is present in the project root.
2. Run the test suite.
3. Run inventory first.
4. Review the generated Google Sheet carefully.
5. Run `move-approved --dry-run` before any real move.
6. Only run `move-approved` without `--dry-run` after the dry run matches your intent.

## Safety rules

- Inventory is the default behavior.
- Files are never deleted.
- Folders are not moved unless explicitly allowed in config.
- Moves only happen when `review_decision` is exactly `APPROVE_MOVE`.
- Move operations support dry run mode.
- Every attempted action is logged to a local CSV file.
- Drive Labels are not required.
- Do not run this tool first on your whole Drive with moves enabled.

## Notes for Windows

- Activate the virtual environment with `.\.venv\Scripts\Activate.ps1`, not `.\.venv\Scripts\activate`.
- If you see script execution policy errors, use the Process-scope bypass command above in the current shell only.
- The project should be run from `C:\Users\Samue\OneDrive\Documents\google-drive-organizer`, not the old folder name.
