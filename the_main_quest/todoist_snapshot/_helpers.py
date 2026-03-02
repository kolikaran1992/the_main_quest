"""Shared helpers for Todoist snapshot pipelines."""

from datetime import date, datetime


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def _parse_duration_minutes(duration_obj: dict | None) -> int | None:
    if not duration_obj:
        return None
    amount = duration_obj.get("amount")
    if amount is None:
        return None
    unit = duration_obj.get("unit", "minute")
    return amount * 1440 if unit == "day" else amount


def _build_task_dim_row(task: dict, projects: dict, sections: dict) -> dict:
    """Extract dimension fields from a Todoist task dict."""
    project_id = task.get("project_id")
    section_id = task.get("section_id")

    return {
        "task_id": task["id"],
        "task_content": task.get("content", ""),
        "task_description": task.get("description") or None,
        "project_id": project_id,
        "project_name": projects.get(project_id) if project_id else None,
        "section_id": section_id,
        "section_name": sections.get(section_id) if section_id else None,
        "parent_task_id": task.get("parent_id") or None,
        "labels": task.get("labels") or [],
        "priority": task.get("priority"),
        "created_at": _parse_ts(task.get("created_at")),
    }
