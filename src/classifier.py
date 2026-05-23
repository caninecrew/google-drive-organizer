from __future__ import annotations

import re

ARCHIVE_PATH_HINTS = [
    "childhood",
    "old personal",
    "old files",
    "games",
    "minecraft",
    "roblox",
    "funny",
    "joke",
    "meme",
    "drawing",
    "story",
    "comic",
]

ROLE_KEYWORDS = {
    "School and Education": ["ttu", "tennessee tech", "vol state", "course", "class", "syllabus", "transcript", "scholarship", "graduation", "ds", "bit"],
    "Scouting": ["scout", "scouting", "bsa", "oa", "order of the arrow", "wa-hi-nasa", "boxwell", "camp", "troop", "lodge", "merit badge", "eagle"],
    "Church and Ministry": ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"],
    "FOIA and Public Records": ["foia", "public records", "open records", "request", "appeal", "pac", "attorney general", "records request", "response letter"],
    "Projects and Coding": ["python", "github", "code", "project", "records tracker", "phase 10", "portfolio", "sql", "flask"],
    "Photos and Media": ["jpg", "jpeg", "png", "heic", "mp4", "mov", "image", "video", "photo"],
    "Work and Career": ["resume", "cover letter", "gideons", "job", "application", "interview", "onboarding", "substitute", "resident assistant", "ra"],
}

ARCHIVE_KEYWORDS = {
    "09 Archive/Childhood and Old Personal Files": ["childhood", "kid", "old personal", "goofy", "funny", "joke", "meme"],
    "09 Archive/Old Random Files": ["random", "misc", "miscellaneous", "old", "untitled", "copy of", "test"],
    "09 Archive/Old Games and Creative Projects": ["minecraft", "roblox", "game", "drawing", "story", "comic", "character", "world", "map", "save", "build"],
    "09 Archive/Delete Later Review": ["delete later review"],
}

SENSITIVITY_KEYWORDS = {
    "Credentials or ID": ["password", "credential", "id card"],
    "Financial": ["tax", "bank"],
    "Legal/Public Records": ["foia", "public records", "open records", "request", "appeal", "records request", "response letter"],
    "School Record": ["transcript"],
    "Student Information": ["student", "scholarship", "class", "course"],
    "Needs Sensitive Review": ["incident", "medical", "ssn", "social security", "driver license"],
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _contains_any(text: str, keywords) -> bool:
    for keyword in keywords:
        if " " in keyword:
            if keyword in text:
                return True
        elif len(keyword) <= 2:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return True
        elif keyword in text:
            return True
    return False


def _path_signal(path_text: str) -> str | None:
    path = _normalize(path_text)
    if not path:
        return None
    if _contains_any(path, ["foia", "public records", "open records", "records request", "attorney general", "appeal", "pac"]):
        return "FOIA and Public Records"
    if _contains_any(path, ["resume", "career", "job", "gideons", "onboarding", "resident assistant", "substitute", "ra"]):
        return "Work and Career"
    if _contains_any(path, ["scouting", "scout", "bsa", "order of the arrow", "oa", "wa hi nasa", "boxwell", "camp", "troop", "lodge", "merit badge", "eagle"]):
        return "Scouting"
    if _contains_any(path, ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"]):
        return "Church and Ministry"
    if _contains_any(path, ["ttu", "tennessee tech", "vol state", "class", "course", "ds", "bit", "transcript", "graduation"]):
        return "School and Education"
    if _contains_any(path, ["python", "github", "code", "project", "records tracker", "phase 10", "portfolio", "sql", "flask"]):
        return "Projects and Coding"
    if _contains_any(path, ARCHIVE_PATH_HINTS) or "archive" in path or "old" in path or "childhood" in path:
        return "Archive"
    return None


def classify_file(name: str, mime_type: str, current_path: str = "") -> tuple[str, str, str, str]:
    text = _normalize(f"{name} {mime_type}")
    path_signal = _path_signal(current_path)
    suggested_role = "Review Later"
    suggested_destination = "99 Review Later"
    suggested_confidence = "Low"

    if path_signal:
        suggested_role = path_signal
        suggested_destination = role_to_destination(path_signal)
        suggested_confidence = "Medium"
        if path_signal == "Archive" and _contains_any(text, ["minecraft", "roblox", "game", "drawing", "story", "comic", "character", "world", "map", "save", "build"]):
            suggested_destination = "09 Archive/Old Games and Creative Projects"
            suggested_confidence = "High"
    elif _contains_any(text, ["untitled"]) and not _contains_any(text, ROLE_KEYWORDS["School and Education"] + ROLE_KEYWORDS["Work and Career"] + ROLE_KEYWORDS["Scouting"] + ROLE_KEYWORDS["Church and Ministry"] + ROLE_KEYWORDS["FOIA and Public Records"] + ROLE_KEYWORDS["Projects and Coding"]):
        suggested_role = "Review Later"
        suggested_destination = "99 Review Later"
        suggested_confidence = "Low"
    else:
        for destination, keywords in ARCHIVE_KEYWORDS.items():
            if _contains_any(text, keywords):
                suggested_role = "Archive"
                suggested_destination = destination
                suggested_confidence = "Low"
                break
        else:
            for role, keywords in ROLE_KEYWORDS.items():
                if _contains_any(text, keywords):
                    suggested_role = role
                    suggested_destination = role_to_destination(role)
                    suggested_confidence = "High"
                    break

    suggested_sensitivity = "Normal"
    for sensitivity, keywords in SENSITIVITY_KEYWORDS.items():
        if _contains_any(text, keywords):
            suggested_sensitivity = sensitivity
            break

    if suggested_role == "Archive" and suggested_destination == "09 Archive/Delete Later Review":
        suggested_confidence = "Low"
    if suggested_role == "Review Later":
        suggested_confidence = "Low"

    return suggested_role, suggested_sensitivity, suggested_destination, suggested_confidence


def role_to_destination(role: str) -> str:
    mapping = {
        "Personal": "01 Personal",
        "School and Education": "02 School and Education",
        "Work and Career": "03 Work and Career",
        "Scouting": "04 Scouting",
        "Church and Ministry": "05 Church and Ministry",
        "FOIA and Public Records": "06 FOIA and Public Records",
        "Projects and Coding": "07 Projects and Coding",
        "Photos and Media": "08 Photos and Media",
        "Archive": "09 Archive",
        "Review Later": "99 Review Later",
    }
    return mapping.get(role, "99 Review Later")


def is_sensitive(sensitivity: str) -> bool:
    return sensitivity != "Normal"


def review_destination_options() -> list[str]:
    return [
        "01 Personal",
        "02 School and Education",
        "03 Work and Career",
        "04 Scouting",
        "05 Church and Ministry",
        "06 FOIA and Public Records",
        "07 Projects and Coding",
        "08 Photos and Media",
        "09 Archive",
        "09 Archive/Childhood and Old Personal Files",
        "09 Archive/Old Random Files",
        "09 Archive/Old Games and Creative Projects",
        "09 Archive/Delete Later Review",
        "99 Review Later",
    ]
