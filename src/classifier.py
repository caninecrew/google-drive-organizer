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
    "School and Education": ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"],
    "Scouting": ["scout", "scouting", "bsa", "oa", "order of the arrow", "wa-hi-nasa", "boxwell", "camp", "troop", "lodge", "merit badge", "eagle"],
    "Church and Ministry": ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"],
    "FOIA and Public Records": ["foia", "public records", "open records", "appeal", "pac", "attorney general", "records request", "response letter"],
    "Projects and Coding": ["python", "github", "code", "coding", "records tracker", "phase 10", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask"],
    "Photos and Media": ["jpg", "jpeg", "png", "heic", "mp4", "mov", "image", "video", "photo"],
    "Work and Career": ["resume", "cover letter", "curriculum vitae", "cv", "job application", "employment", "gideons", "onboarding", "offer letter", "reference list", "substitute teaching", "resident assistant"],
}

ARCHIVE_KEYWORDS = {
    "09 Archive/Childhood and Old Personal Files": ["childhood", "kid", "old personal", "goofy", "funny", "joke", "meme"],
    "09 Archive/Old Random Files": ["random", "misc", "miscellaneous", "old", "copy of", "test"],
    "09 Archive/Old Games and Creative Projects": ["minecraft", "roblox", "game", "drawing", "story", "comic", "character", "world", "map", "save", "build"],
    "09 Archive/Delete Later Review": ["delete later review"],
}

SENSITIVITY_KEYWORDS = {
    "Credentials or ID": ["password", "credential", "id card"],
    "Financial": ["tax", "bank"],
    "Legal/Public Records": ["foia", "public records", "open records", "request", "appeal", "records request", "response letter"],
    "School Record": ["transcript"],
    "Student Information": ["student id", "student record", "student names", "roster", "grade", "grades", "resident incident", "conduct", "ferpa", "transcript"],
    "Needs Sensitive Review": ["incident", "medical", "ssn", "social security", "driver license"],
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _contains_any(text: str, keywords) -> bool:
    for keyword in keywords:
        if " " in keyword or "." in keyword:
            if keyword in text:
                return True
        elif len(keyword) <= 2:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return True
        elif keyword in text:
            return True
    return False


def _contains_standalone_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text))


def _weak_untitled(text: str) -> bool:
    return "untitled" in text


def _path_signal(path_text: str) -> str | None:
    path = _normalize(path_text)
    if not path:
        return None
    if _contains_any(path, ["foia", "public records", "open records", "records request", "attorney general", "appeal", "pac"]):
        return "FOIA and Public Records"
    if _contains_any(path, ["resume", "career", "job", "gideons", "onboarding", "resident assistant", "substitute", "employment", "offer letter"]):
        return "Work and Career"
    if _contains_any(path, ["scouting", "scout", "bsa", "order of the arrow", "oa", "wa hi nasa", "boxwell", "camp", "troop", "lodge", "merit badge", "eagle"]):
        return "Scouting"
    if _contains_any(path, ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"]):
        return "Church and Ministry"
    if _contains_any(path, ["ttu", "tennessee tech", "vol state", "ds", "bit", "transcript", "graduation"]):
        return "School and Education"
    if _contains_any(path, ["python", "github", "code", "coding", "records tracker", "phase 10", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask"]):
        return "Projects and Coding"
    if _contains_any(path, ARCHIVE_PATH_HINTS) or "archive" in path or "old personal" in path or "childhood" in path:
        return "Archive"
    return None


def _work_context_signal(text: str, path_text: str) -> bool:
    return _contains_any(text, ["resume", "cover letter", "curriculum vitae", "job application", "employment", "gideons", "onboarding", "offer letter", "reference list", "substitute teaching", "resident assistant"]) or (
        _contains_any(text, ["interview"]) and _contains_any(path_text, ["job", "career", "employment", "hiring", "gideons", "substitute", "resident assistant"])
    ) or (_contains_standalone_token(text, "ra") and _contains_any(path_text, ["housing", "residence life", "resident", "job", "career", "employment"]))


def _projects_context_signal(text: str, path_text: str) -> bool:
    tech_terms = ["python", "github", "code", "coding", "records tracker", "phase 10", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask"]
    return _contains_any(text, tech_terms) or _contains_any(path_text, tech_terms)


def _school_context_signal(text: str, path_text: str) -> bool:
    school_terms = ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"]
    return _contains_any(text, school_terms) or _contains_any(path_text, ["school", "ttu", "tennessee tech", "vol state", "class", "course"])


def classify_file(name: str, mime_type: str, current_path: str = "") -> tuple[str, str, str, str]:
    name_text = _normalize(name)
    mime_text = _normalize(mime_type)
    text = _normalize(f"{name} {mime_type}")
    path_text = _normalize(current_path)
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
    elif _weak_untitled(name_text):
        suggested_role = "Review Later"
        suggested_destination = "99 Review Later"
        suggested_confidence = "Low"
    else:
        archive_text = text if not path_text else f"{text} {path_text}"
        archive_match = False
        if not _weak_untitled(name_text):
            archive_match = any(_contains_any(archive_text, keywords) for keywords in ARCHIVE_KEYWORDS.values())
        if archive_match:
            for destination, keywords in ARCHIVE_KEYWORDS.items():
                if _contains_any(archive_text, keywords):
                    suggested_role = "Archive"
                    suggested_destination = destination
                    suggested_confidence = "Low"
                    break
        elif _contains_any(name_text, ["application"]) and not (_contains_any(path_text, ["scouting", "school", "ttu", "tennessee tech", "vol state", "foia", "public records"]) or _work_context_signal(text, path_text)):
            suggested_role = "Review Later"
            suggested_destination = "99 Review Later"
            suggested_confidence = "Low"
        elif _work_context_signal(text, path_text):
            suggested_role = "Work and Career"
            suggested_destination = role_to_destination("Work and Career")
            suggested_confidence = "High"
        elif _projects_context_signal(text, path_text):
            suggested_role = "Projects and Coding"
            suggested_destination = role_to_destination("Projects and Coding")
            suggested_confidence = "High"
        elif _school_context_signal(text, path_text):
            suggested_role = "School and Education"
            suggested_destination = role_to_destination("School and Education")
            suggested_confidence = "High" if any(term in text for term in ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"]) else "Medium"
        else:
            for role, keywords in ROLE_KEYWORDS.items():
                if role in {"Work and Career", "Projects and Coding", "School and Education"}:
                    continue
                if _contains_any(text, keywords) or _contains_any(path_text, keywords):
                    suggested_role = role
                    suggested_destination = role_to_destination(role)
                    suggested_confidence = "High" if _contains_any(text, keywords) else "Medium"
                    break

    suggested_sensitivity = "Normal"
    if _contains_any(text, ["transcript"]):
        suggested_sensitivity = "School Record"
    elif _contains_any(text, ["student id", "student record", "roster", "grade", "grades", "resident incident", "conduct", "ferpa"]):
        suggested_sensitivity = "Student Information"
    elif _contains_any(text, ["incident", "medical", "ssn", "social security", "driver license"]):
        suggested_sensitivity = "Needs Sensitive Review"
    elif _contains_any(text, ["tax", "bank"]):
        suggested_sensitivity = "Financial"
    elif _contains_any(text, ["password", "credential", "id card"]):
        suggested_sensitivity = "Credentials or ID"
    elif _contains_any(text, ["foia", "public records", "open records", "request", "appeal", "records request", "response letter"]):
        suggested_sensitivity = "Legal/Public Records"

    if suggested_sensitivity == "Student Information" and not _contains_any(text, ["student id", "student record", "roster", "grade", "grades", "resident incident", "conduct", "ferpa", "transcript"]):
        if _contains_any(text, ["class", "course", "syllabus", "merit badge class", "university of scouting"]):
            suggested_sensitivity = "Normal"

    if suggested_role == "Archive" and suggested_destination == "09 Archive/Delete Later Review":
        suggested_confidence = "Low"
    if suggested_role == "Review Later":
        suggested_confidence = "Low"
    if "unknown parent" in current_path.lower() or "[unresolved parent]" in current_path.lower():
        if suggested_confidence == "High":
            suggested_confidence = "Medium"
    if _weak_untitled(name_text) and path_signal is None and suggested_role == "Archive":
        suggested_role = "Review Later"
        suggested_destination = "99 Review Later"
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
