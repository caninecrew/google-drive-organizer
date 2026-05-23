# Google Drive Organizer

Safe Google Drive organization assistant for personal use.

## What it does

- Inventories non-trashed files from My Drive.
- Writes review rows to Google Sheets.
- Suggests categories, destination folders, sensitivity, and activity metadata.
- Moves only files that you explicitly approve in the review sheet.
- Never deletes files.

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

## Safety rules

- Inventory is the default behavior.
- Files are never deleted.
- Folders are not moved unless explicitly allowed in config.
- Moves only happen when `review_decision` is exactly `APPROVE_MOVE`.
- Move operations support dry run mode.
- Every attempted action is logged to a local CSV file.
- Drive Labels are not required.

