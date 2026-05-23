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

PERSONAL_FAMILY_HISTORY_DESTINATION = "01 Personal/Family History"
PERSONAL_FAMILY_HISTORY_VIDEO_DESTINATION = "01 Personal/Family History/Video Interviews"
SCOUTING_PHOTOS_DESTINATION = "04 Scouting/Photos"
MEDIA_SCOUTING_PHOTOS_DESTINATION = "08 Photos and Media/Scouting Photos"
MEDIA_FAMILY_HISTORY_VIDEOS_DESTINATION = "08 Photos and Media/Family History Videos"

ROLE_KEYWORDS = {
    "School and Education": ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"],
    "Scouting": ["scout", "scouting", "bsa", "oa", "order of the arrow", "wa-hi-nasa", "boxwell", "camp", "troop", "lodge", "merit badge", "eagle"],
    "Church and Ministry": ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"],
    "FOIA and Public Records": ["foia", "public records", "open records", "appeal", "pac", "attorney general", "records request", "response letter"],
    "Projects and Coding": ["python", "github", "code", "coding", "records tracker", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask", "development", "app"],
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
        elif len(keyword) <= 4:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return True
        elif keyword in text:
            return True
    return False


def _contains_standalone_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text))


def _weak_untitled(text: str) -> bool:
    return "untitled" in text


def _contains_archive_terms(text: str) -> bool:
    return _contains_any(text, ARCHIVE_PATH_HINTS + ["random", "misc", "miscellaneous", "old", "copy of", "test", "game", "games"])


def _is_family_history_media(text: str, path_text: str) -> bool:
    return _contains_any(text, ["family history", "video interview", "interview video"]) or _contains_any(
        path_text, ["family history", "video interview", "interviews"]
    )


def _is_scouting_media(text: str, path_text: str) -> bool:
    return _contains_any(text, ["scouting", "scout", "bsa", "oa", "order of the arrow", "wa-hi-nasa", "boxwell", "troop", "lodge"]) or _contains_any(
        path_text, ["scouting", "scout", "bsa", "oa", "order of the arrow", "wa-hi-nasa", "boxwell", "troop", "lodge"]
    )


def _is_church_media(text: str, path_text: str) -> bool:
    return _contains_any(text, ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"]) or _contains_any(
        path_text, ["church", "nazarene", "grace", "ministry", "sermon", "lesson", "vbs", "mission", "kenya", "youth", "children"]
    )


def _is_media_mime(mime_type: str) -> bool:
    return _contains_any(_normalize(mime_type), ["image", "video"]) or _contains_any(mime_type, ["jpg", "jpeg", "png", "heic", "mp4", "mov"])


def _is_family_history_destination_candidate(text: str, path_text: str) -> bool:
    return _contains_any(text, ["family history", "video interview", "interview", "old family", "family video"]) or _contains_any(
        path_text, ["family history", "family", "interview"]
    )


def _has_development_context(text: str, path_text: str) -> bool:
    return _contains_any(text, ["python", "github", "repo", "app", "source", "code", "implementation", "development", "coding", "sql", "flask", ".py", ".ipynb", ".js", ".html", "database", "api"]) or _contains_any(
        path_text, ["python", "github", "repo", "app", "source", "code", "implementation", "development", "coding", "sql", "flask", "database", "api"]
    )


def _work_interview_context(text: str, path_text: str) -> bool:
    return _contains_any(text, ["interview"]) and _contains_any(path_text, ["job", "career", "employment", "hiring", "gideons", "substitute", "resident assistant"])


def _school_transcript_context(text: str, path_text: str) -> bool:
    if not _contains_any(text, ["transcript"]):
        return False
    academic_terms = ["ttu", "tennessee tech", "vol state", "school", "academic", "grade", "grades", "semester", "class schedule", "schedule", "student"]
    return _contains_any(text, ["high school transcript", "tn tech transcript", "ttu transcript", "tennessee tech transcript", "academic transcript", "school transcript"]) or _contains_any(path_text, academic_terms)


def _financial_context(text: str, path_text: str) -> bool:
    financial_terms = ["bank statement", "bank account", "banking", "invoice", "receipt", "budget", "payment", "tax return", "financial aid", "tax", "check", "ledger", "balance", "invoice", "bill"]
    if _contains_any(text, ["word bank", "wilson bank and trust"]):
        return False
    if _contains_any(text, ["bank"]) and _contains_any(path_text, ["scouting", "church", "personal"]):
        return False
    return _contains_any(text, financial_terms) or _contains_any(path_text, ["finance", "financial", "accounting", "tax"])


def _student_information_context(text: str, path_text: str) -> bool:
    strong_terms = ["student id", "student record", "roster", "grade", "grades", "resident incident", "ferpa", "discipline", "student", "incident report"]
    if _contains_any(text, ["fall"]) and not _contains_any(path_text, ["semester", "transcript", "grade", "class schedule", "school", "academic"]):
        return False
    if _contains_any(text, ["conduct"]) and not _contains_any(text, ["student", "resident", "discipline", "incident", "case"]):
        return False
    if _contains_any(text, ["class", "course", "review", "syllabus", "university of scouting", "merit badge class"]) and not _contains_any(path_text, ["student", "school", "academic", "semester", "class schedule"]):
        return False
    return _contains_any(text, strong_terms) or (_contains_any(text, ["schedule"]) and _contains_any(path_text, ["school", "student", "academic", "semester", "class"]))


def _media_destination_for_context(text: str, path_text: str, media_policy: str, current_role: str) -> tuple[str | None, str | None]:
    if not _is_media_mime(text):
        return None, None
    if _is_family_history_media(text, path_text):
        if media_policy == "media_first":
            return MEDIA_FAMILY_HISTORY_VIDEOS_DESTINATION, "Medium"
        return PERSONAL_FAMILY_HISTORY_VIDEO_DESTINATION, "Medium"
    if _is_scouting_media(text, path_text):
        if media_policy == "media_first":
            return MEDIA_SCOUTING_PHOTOS_DESTINATION, "Medium"
        if current_role == "Scouting":
            return SCOUTING_PHOTOS_DESTINATION, "Medium"
    if _is_church_media(text, path_text) and media_policy == "media_first":
        return "08 Photos and Media", "Medium"
    return None, None


def _path_signal(path_text: str) -> str | None:
    path = _normalize(path_text)
    if not path:
        return None
    if "academic and career" in path:
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
    if _contains_any(path, ["python", "github", "code", "coding", "records tracker", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask"]):
        return "Projects and Coding"
    if _contains_any(path, ARCHIVE_PATH_HINTS) or "archive" in path or "old personal" in path or "childhood" in path:
        return "Archive"
    return None


def _work_context_signal(text: str, path_text: str) -> bool:
    return _contains_any(text, ["resume", "cover letter", "curriculum vitae", "job application", "employment", "gideons", "onboarding", "offer letter", "reference list", "substitute teaching", "resident assistant"]) or (
        _contains_any(text, ["interview"]) and _contains_any(path_text, ["job", "career", "employment", "hiring", "gideons", "substitute", "resident assistant"])
    ) or (_contains_standalone_token(text, "ra") and _contains_any(path_text, ["housing", "residence life", "resident", "job", "career", "employment"]))


def _projects_context_signal(text: str, path_text: str) -> bool:
    tech_terms = ["python", "github", "repo", "code", "coding", "records tracker", "portfolio website", ".py", ".ipynb", ".js", ".html", "database", "api", "sql", "flask", "development", "implementation", "source", "app"]
    return _contains_any(text, tech_terms) or _contains_any(path_text, tech_terms)


def _school_context_signal(text: str, path_text: str) -> bool:
    school_terms = ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"]
    return _contains_any(text, school_terms) or _contains_any(path_text, ["school", "ttu", "tennessee tech", "vol state", "class", "course", "academic and career"])


def classify_file(name: str, mime_type: str, current_path: str = "", media_policy: str = "role_first") -> tuple[str, str, str, str]:
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
        if path_signal == "Archive" and _contains_archive_terms(text):
            suggested_destination = "09 Archive/Old Games and Creative Projects"
            suggested_confidence = "High"
    elif _weak_untitled(name_text):
        suggested_role = "Review Later"
        suggested_destination = "99 Review Later"
        suggested_confidence = "Low"
    else:
        media_signal = _is_media_mime(mime_type) or _contains_any(text, ["photo", "video", "image", "jpg", "jpeg", "png", "heic", "mp4", "mov"])
        archive_text = text if not path_text else f"{text} {path_text}"
        archive_match = False
        if not _weak_untitled(name_text) and not _is_family_history_media(text, path_text):
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
        elif "academic and career" in path_text:
            if _work_context_signal(text, path_text):
                suggested_role = "Work and Career"
                suggested_destination = role_to_destination("Work and Career")
                suggested_confidence = "High"
            elif _school_context_signal(text, path_text) or _contains_any(name_text, ["acct", "accounting", "cheat sheet", "study"]):
                suggested_role = "School and Education"
                suggested_destination = role_to_destination("School and Education")
                suggested_confidence = "Medium"
            else:
                suggested_role = "Review Later"
                suggested_destination = "99 Review Later"
                suggested_confidence = "Low"
        elif _work_context_signal(text, path_text):
            suggested_role = "Work and Career"
            suggested_destination = role_to_destination("Work and Career")
            suggested_confidence = "High"
        elif "phase 10" in text and not _has_development_context(text, path_text):
            suggested_role = "Review Later"
            suggested_destination = "99 Review Later"
            suggested_confidence = "Low"
        elif "code of conduct" in text or "personal code of conduct" in text:
            suggested_role = "Review Later"
            suggested_destination = "99 Review Later"
            suggested_confidence = "Low"
        elif _projects_context_signal(text, path_text) and not _contains_any(text, ["code of conduct", "personal code of conduct"]):
            suggested_role = "Projects and Coding"
            suggested_destination = role_to_destination("Projects and Coding")
            suggested_confidence = "High"
        elif _is_family_history_media(text, path_text) and media_signal:
            suggested_role = "Personal"
            suggested_destination = PERSONAL_FAMILY_HISTORY_DESTINATION
            suggested_confidence = "Medium"
        elif _is_scouting_media(text, path_text) and media_signal:
            suggested_role = "Scouting"
            suggested_destination = SCOUTING_PHOTOS_DESTINATION if media_policy == "media_first" else "04 Scouting"
            suggested_confidence = "Medium"
        elif _is_church_media(text, path_text) and media_signal:
            suggested_role = "Church and Ministry"
            suggested_destination = "05 Church and Ministry"
            suggested_confidence = "Medium"
        elif media_signal:
            suggested_role = "Photos and Media"
            suggested_destination = role_to_destination("Photos and Media")
            suggested_confidence = "High"
        elif _school_context_signal(text, path_text):
            suggested_role = "School and Education"
            suggested_destination = role_to_destination("School and Education")
            suggested_confidence = "High" if any(term in text for term in ["ttu", "tennessee tech", "vol state", "transcript", "graduation", "ds", "bit"]) else "Medium"
        else:
            if _contains_any(text, ["foia", "public records", "open records", "appeal", "pac", "attorney general", "records request", "response letter"]) or _contains_any(path_text, ["foia", "public records", "open records", "appeal", "pac", "attorney general", "records request"]):
                suggested_role = "FOIA and Public Records"
                suggested_destination = "06 FOIA and Public Records"
                suggested_confidence = "High"
            else:
                for role, keywords in ROLE_KEYWORDS.items():
                    if role in {"Work and Career", "Projects and Coding", "School and Education", "Photos and Media"}:
                        continue
                    if _contains_any(text, keywords) or _contains_any(path_text, keywords):
                        suggested_role = role
                        suggested_destination = role_to_destination(role)
                        suggested_confidence = "High" if _contains_any(text, keywords) else "Medium"
                        break

    media_destination, media_confidence = _media_destination_for_context(text, path_text, media_policy, suggested_role)
    if media_destination and suggested_role in {"Scouting", "Church and Ministry", "Personal"}:
        suggested_destination = media_destination
        if media_confidence:
            suggested_confidence = media_confidence

    suggested_sensitivity = "Normal"
    if _school_transcript_context(text, path_text):
        suggested_sensitivity = "School Record"
    elif _student_information_context(text, path_text):
        suggested_sensitivity = "Student Information"
    elif _contains_any(text, ["conduct"]):
        if _contains_any(text, ["code of conduct", "personal code of conduct"]):
            suggested_sensitivity = "Normal"
        elif _contains_any(path_text, ["student", "resident", "school"]) or _contains_any(text, ["student", "resident", "discipline", "case", "incident"]):
            suggested_sensitivity = "Needs Sensitive Review"
    elif _contains_any(text, ["incident", "medical", "ssn", "social security", "driver license"]):
        suggested_sensitivity = "Needs Sensitive Review"
    elif _contains_any(text, ["tax", "bank"]):
        if _financial_context(text, path_text):
            suggested_sensitivity = "Financial"
    elif _contains_any(text, ["password", "credential", "id card"]):
        suggested_sensitivity = "Credentials or ID"
    elif _contains_any(text, ["foia", "public records", "open records", "request", "appeal", "records request", "response letter"]):
        suggested_sensitivity = "Legal/Public Records"

    if suggested_sensitivity == "Student Information" and not _contains_any(text, ["student id", "student record", "roster", "grade", "grades", "resident incident", "conduct", "ferpa", "transcript"]):
        if _contains_any(text, ["class", "course", "syllabus", "merit badge class", "university of scouting", "fall"]):
            suggested_sensitivity = "Normal"

    if suggested_role == "Archive" and suggested_destination == "09 Archive/Delete Later Review":
        suggested_confidence = "Low"
    if suggested_role == "Review Later":
        suggested_confidence = "Low"
    if "unknown parent" in current_path.lower() or "[unresolved parent]" in current_path.lower():
        if suggested_confidence == "High":
            suggested_confidence = "Medium"
    if "academic and career" in path_text and suggested_confidence == "High" and suggested_role in {"School and Education", "Review Later"}:
        suggested_confidence = "Medium"
    if _weak_untitled(name_text) and path_signal is None and suggested_role == "Archive":
        suggested_role = "Review Later"
        suggested_destination = "99 Review Later"
        suggested_confidence = "Low"
    if _weak_untitled(name_text) and path_signal and suggested_role != path_signal:
        suggested_confidence = "Low"
    if "unknown parent" in current_path.lower() or "[unresolved parent]" in current_path.lower():
        if suggested_confidence == "High":
            suggested_confidence = "Medium"
        elif suggested_confidence == "Medium":
            suggested_confidence = "Low"

    return suggested_role, suggested_sensitivity, suggested_destination, suggested_confidence


def role_to_destination(role: str) -> str:
    mapping = {
        "Personal": "01 Personal",
        "Personal/Family History": "01 Personal/Family History",
        "School and Education": "02 School and Education",
        "Work and Career": "03 Work and Career",
        "Scouting": "04 Scouting",
        "Scouting/Photos": "04 Scouting/Photos",
        "Church and Ministry": "05 Church and Ministry",
        "FOIA and Public Records": "06 FOIA and Public Records",
        "Projects and Coding": "07 Projects and Coding",
        "Photos and Media": "08 Photos and Media",
        "Photos and Media/Scouting Photos": "08 Photos and Media/Scouting Photos",
        "Photos and Media/Family History Videos": "08 Photos and Media/Family History Videos",
        "Archive": "09 Archive",
        "Archive/Childhood and Old Personal Files": "09 Archive/Childhood and Old Personal Files",
        "Archive/Old Random Files": "09 Archive/Old Random Files",
        "Archive/Old Games and Creative Projects": "09 Archive/Old Games and Creative Projects",
        "Archive/Delete Later Review": "09 Archive/Delete Later Review",
        "Review Later": "99 Review Later",
    }
    return mapping.get(role, "99 Review Later")


def is_sensitive(sensitivity: str) -> bool:
    return sensitivity != "Normal"


def review_destination_options() -> list[str]:
    return [
        "01 Personal",
        "01 Personal/Family History",
        "01 Personal/Family History/Video Interviews",
        "02 School and Education",
        "03 Work and Career",
        "04 Scouting",
        "04 Scouting/Photos",
        "05 Church and Ministry",
        "06 FOIA and Public Records",
        "07 Projects and Coding",
        "08 Photos and Media",
        "08 Photos and Media/Scouting Photos",
        "08 Photos and Media/Family History Videos",
        "09 Archive",
        "09 Archive/Childhood and Old Personal Files",
        "09 Archive/Old Random Files",
        "09 Archive/Old Games and Creative Projects",
        "09 Archive/Delete Later Review",
        "99 Review Later",
    ]
