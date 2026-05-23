from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    include_folders: bool = False
    activity_enrichment: bool = False
    allow_create_missing_destination_folders: bool = False
    allow_move_folders: bool = False
    allow_move_shortcuts: bool = False
    media_policy: str = "role_first"
    review_spreadsheet_prefix: str = "Google Drive Organizer Review"
    log_dir: str = "data/logs"


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig(
        include_folders=bool(data.get("include_folders", False)),
        activity_enrichment=bool(data.get("activity_enrichment", False)),
        allow_create_missing_destination_folders=bool(
            data.get("allow_create_missing_destination_folders", False)
        ),
        allow_move_folders=bool(data.get("allow_move_folders", False)),
        allow_move_shortcuts=bool(data.get("allow_move_shortcuts", False)),
        media_policy=str(data.get("media_policy", "role_first")),
        review_spreadsheet_prefix=str(
            data.get("review_spreadsheet_prefix", "Google Drive Organizer Review")
        ),
        log_dir=str(data.get("log_dir", "data/logs")),
    )
