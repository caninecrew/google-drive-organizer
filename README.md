# google-drive-organizer

Safe Google Drive organization assistant for personal use.

## What it does

- Inventories non-trashed files from My Drive.
- Writes review rows to Google Sheets.
- Suggests categories, destination folders, sensitivity, and activity metadata.
- Includes a readable `current_path` column so folder context can influence review decisions.
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

## Review workflow

1. Run inventory.
2. Open the generated spreadsheet.
3. Review suggestions and set `review_decision` to `APPROVE_MOVE` only for rows you want moved.
4. Set `final_destination` if you want to override the suggested destination.
5. Run `move-approved` with `--dry-run` first.
6. Run `move-approved` without `--dry-run` only after confirming the dry run output.

## Why `current_path` matters

- Classification now uses both filename and folder path.
- A goofy or untitled filename inside a school, FOIA, work, or scouting folder may still be serious.
- `current_path` helps review old, ambiguous, or inherited files without forcing them into archive buckets too early.

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
