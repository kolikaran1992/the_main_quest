"""Todoist API layer — authentication, pagination, and endpoint helpers."""

import requests

from the_main_quest.omniconf import config, logger

_BASE = "https://api.todoist.com/api/v1"


def _headers() -> dict:
    """Bearer auth header. Never log the return value."""
    return {"Authorization": f"Bearer {config.todoist.api_token}"}


def _fetch_all_pages(url: str, results_key: str, params: dict | None = None) -> list:
    """Cursor-paginated GET; returns all pages combined into a single list."""
    items = []
    cursor = None

    while True:
        p = dict(params or {})
        if cursor:
            p["cursor"] = cursor

        resp = requests.get(url, headers=_headers(), params=p, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        items.extend(data.get(results_key, []))

        cursor = data.get("next_cursor")
        if not cursor:
            break

    return items


def fetch_active_tasks() -> list:
    """Return all active tasks via GET /api/v1/tasks."""
    return _fetch_all_pages(f"{_BASE}/tasks", "results")


def fetch_completed_today() -> tuple[list, bool]:
    """
    Fetch tasks completed today via the Pro-plan endpoint.

    Returns (items, pro_available).
    Falls back to ([], False) on 403 (free plan).
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    params = {
        "since": now.strftime("%Y-%m-%dT00:00:00Z"),
        "until": now.strftime("%Y-%m-%dT23:59:59Z"),
    }

    url = f"{_BASE}/tasks/completed/by_completion_date"
    items: list = []
    cursor = None

    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor

        resp = requests.get(url, headers=_headers(), params=p, timeout=30)

        if resp.status_code == 403:
            logger.info("Completed-tasks endpoint returned 403 — free plan, using fallback")
            return [], False

        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("items", []))

        cursor = data.get("next_cursor")
        if not cursor:
            break

    return items, True


def fetch_projects() -> dict:
    """Return {project_id: project_name} for all projects."""
    projects = _fetch_all_pages(f"{_BASE}/projects", "results")
    return {p["id"]: p["name"] for p in projects}


def fetch_sections() -> dict:
    """Return {section_id: section_name} for all sections."""
    sections = _fetch_all_pages(f"{_BASE}/sections", "results")
    return {s["id"]: s["name"] for s in sections}
