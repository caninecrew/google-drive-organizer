from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SummaryResult:
    total_rows: int
    by_role: Counter
    by_destination: Counter
    by_confidence: Counter
    by_sensitivity: Counter
    unknown_parent_count: int
    unresolved_parent_count: int
    untitled_count: int
    untitled_by_role: Counter
    low_confidence_count: int
    low_confidence_approve_move_count: int
    warnings: list[str]


def load_inventory_rows(csv_path: str | Path) -> list[dict[str, str]]:
    with Path(csv_path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_latest_inventory_csv(exports_dir: str | Path = "data/exports") -> Path | None:
    exports_path = Path(exports_dir)
    candidates = sorted(
        exports_path.glob("inventory_*.csv"),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    if not candidates:
        return None
    return candidates[-1]


def summarize_rows(rows: list[dict[str, str]]) -> SummaryResult:
    by_role = Counter()
    by_destination = Counter()
    by_confidence = Counter()
    by_sensitivity = Counter()
    untitled_by_role = Counter()

    unknown_parent_count = 0
    unresolved_parent_count = 0
    untitled_count = 0
    low_confidence_count = 0
    low_confidence_approve_move_count = 0

    for row in rows:
        role = row.get("suggested_role", "")
        destination = row.get("suggested_destination", "")
        confidence = row.get("suggested_confidence", "")
        sensitivity = row.get("suggested_sensitivity", "")
        current_path = row.get("current_path", "")
        name = row.get("name", "")
        review_decision = row.get("review_decision", "")

        by_role[role] += 1
        by_destination[destination] += 1
        by_confidence[confidence] += 1
        by_sensitivity[sensitivity] += 1

        if "Unknown Parent" in current_path:
            unknown_parent_count += 1
        if "[unresolved parent]" in current_path:
            unresolved_parent_count += 1
        if "Untitled" in name:
            untitled_count += 1
            untitled_by_role[role] += 1
        if confidence == "Low":
            low_confidence_count += 1
            if review_decision == "APPROVE_MOVE":
                low_confidence_approve_move_count += 1

    warnings = build_warnings(
        total_rows=len(rows),
        unknown_parent_count=unknown_parent_count,
        work_and_career_count=by_role.get("Work and Career", 0),
        untitled_count=untitled_count,
        untitled_archive_count=untitled_by_role.get("Archive", 0),
        low_confidence_approve_move_count=low_confidence_approve_move_count,
    )
    return SummaryResult(
        total_rows=len(rows),
        by_role=by_role,
        by_destination=by_destination,
        by_confidence=by_confidence,
        by_sensitivity=by_sensitivity,
        unknown_parent_count=unknown_parent_count,
        unresolved_parent_count=unresolved_parent_count,
        untitled_count=untitled_count,
        untitled_by_role=untitled_by_role,
        low_confidence_count=low_confidence_count,
        low_confidence_approve_move_count=low_confidence_approve_move_count,
        warnings=warnings,
    )


def build_warnings(*, total_rows: int, unknown_parent_count: int, work_and_career_count: int, untitled_count: int, untitled_archive_count: int, low_confidence_approve_move_count: int) -> list[str]:
    warnings = []
    if total_rows and unknown_parent_count / total_rows > 0.25:
        warnings.append("More than 25% of rows have Unknown Parent.")
    if total_rows and work_and_career_count / total_rows > 0.10:
        warnings.append("More than 10% of rows are Work and Career.")
    if untitled_count and untitled_archive_count / untitled_count > 0.10:
        warnings.append("More than 10% of Untitled files are assigned to Archive.")
    if low_confidence_approve_move_count:
        warnings.append("Some Low confidence rows are marked APPROVE_MOVE.")
    return warnings


def write_summary_export(summary: SummaryResult, export_path: str | Path) -> Path:
    path = Path(export_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            writer.writerow(["total_rows", summary.total_rows])
            writer.writerow(["unknown_parent_count", summary.unknown_parent_count])
            writer.writerow(["unresolved_parent_count", summary.unresolved_parent_count])
            writer.writerow(["untitled_count", summary.untitled_count])
            writer.writerow(["low_confidence_count", summary.low_confidence_count])
            for key, value in summary.by_role.items():
                writer.writerow([f"suggested_role:{key}", value])
            for key, value in summary.by_destination.items():
                writer.writerow([f"suggested_destination:{key}", value])
            for key, value in summary.by_confidence.items():
                writer.writerow([f"suggested_confidence:{key}", value])
            for key, value in summary.by_sensitivity.items():
                writer.writerow([f"suggested_sensitivity:{key}", value])
    else:
        with path.open("w", encoding="utf-8") as f:
            f.write(format_summary(summary))
    return path


def format_summary(summary: SummaryResult) -> str:
    lines = [
        f"total rows: {summary.total_rows}",
        f"count of current_path containing \"Unknown Parent\": {summary.unknown_parent_count}",
        f"count of current_path containing \"[unresolved parent]\": {summary.unresolved_parent_count}",
        f"count of filenames containing \"Untitled\": {summary.untitled_count}",
        f"count of rows where suggested_confidence = Low: {summary.low_confidence_count}",
        "",
        "count by suggested_role:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in summary.by_role.items())
    lines.append("count by suggested_destination:")
    lines.extend(f"  {key}: {value}" for key, value in summary.by_destination.items())
    lines.append("count by suggested_confidence:")
    lines.extend(f"  {key}: {value}" for key, value in summary.by_confidence.items())
    lines.append("count by suggested_sensitivity:")
    lines.extend(f"  {key}: {value}" for key, value in summary.by_sensitivity.items())
    lines.append("count of Untitled files by suggested_role:")
    lines.extend(f"  {key}: {value}" for key, value in summary.untitled_by_role.items())
    if summary.warnings:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in summary.warnings)
    return "\n".join(lines) + "\n"
