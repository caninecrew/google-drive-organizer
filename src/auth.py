from __future__ import annotations

from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.activity.readonly",
]


def get_credentials(credentials_path: str | Path = "credentials.json", token_path: str | Path = "token.json") -> Credentials:
    credentials_file = Path(credentials_path)
    token_file = Path(token_path)
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds
    if not credentials_file.exists():
        raise FileNotFoundError("credentials.json not found in project root")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_service(api_name: str, version: str, credentials: Credentials):
    return build(api_name, version, credentials=credentials, cache_discovery=False)


def get_drive_service(credentials: Credentials):
    return build_service("drive", "v3", credentials)


def get_sheets_service(credentials: Credentials):
    return build_service("sheets", "v4", credentials)


def get_drive_activity_service(credentials: Credentials):
    return build_service("driveactivity", "v2", credentials)

