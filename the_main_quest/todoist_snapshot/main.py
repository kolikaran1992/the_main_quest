"""
Todoist daily snapshot orchestrator.

Fetch → upsert dimensions (SCD Type 2) → insert facts → log summary.
Run via cron at 23:55: poetry run python -m the_main_quest.todoist_snapshot.main
"""

import logging
import sys
from datetime import date, datetime

import pytz
from pythonjsonlogger import jsonlogger

from the_main_quest.omniconf import config
from the_main_quest.omniconf import logger as _base_logger

from .db import get_conn, insert_recurring_facts, insert_snapshot_facts, upsert_task_dimension
from .fetcher import fetch_active_tasks, fetch_completed_today, fetch_projects, fetch_sections

# ---------------------------------------------------------------------------
# Loki logging setup
# Must be done before any log calls so that all output lands in the right file.
# We cannot use add_loki_handler() because it writes to ~/Data/... with a
# project-name-derived filename; the Promtail catch-all requires /tmp/loki_*.log.
# ---------------------------------------------------------------------------
_LOKI_PATH = "/tmp/loki_todoist_snapshot.log"

_file_handler = logging.FileHandler(_LOKI_PATH)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(
    jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
)
_base_logger.addHandler(_file_handler)

log = logging.LoggerAdapter(_base_logger, {"project": "todoist_snapshot"})

# ---------------------------------------------------------------------------
# Table names — read from config so tests can point at _test tables
# ---------------------------------------------------------------------------
_T_TASKS = config.todoist_snapshot.tasks_table
_T_SNAPSHOT = config.todoist_snapshot.snapshot_table
_T_REC_TASKS = config.todoist_snapshot.recurring_tasks_table
_T_REC_LOG = config.todoist_snapshot.recurring_log_table

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    deadline_obj = task.get("deadline")

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


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run() -> None:
    tz = pytz.timezone(config.tz)
    now_ts = datetime.now(tz)
    today = now_ts.date()

    log.info("todoist_snapshot starting", extra={"snapshot_date": today.isoformat()})

    # ------------------------------------------------------------------
    # 1. Fetch
    # ------------------------------------------------------------------
    try:
        active_tasks = fetch_active_tasks()
        completed_today, pro_plan = fetch_completed_today()
        projects = fetch_projects()
        sections = fetch_sections()
    except Exception:
        log.exception("Failed during API fetch — aborting")
        sys.exit(1)

    log.info(
        "fetch complete",
        extra={
            "active_tasks": len(active_tasks),
            "completed_today": len(completed_today),
            "pro_plan": pro_plan,
        },
    )

    # ------------------------------------------------------------------
    # 2. Partition active tasks
    # ------------------------------------------------------------------
    recurring = [t for t in active_tasks if (t.get("due") or {}).get("is_recurring")]
    regular = [t for t in active_tasks if not (t.get("due") or {}).get("is_recurring")]

    active_task_ids = {t["id"] for t in active_tasks}

    # completed_ids: set of task_ids completed today (pro plan only)
    completed_ids: set[str] = {item["task_id"] for item in completed_today} if pro_plan else set()

    # completed_today lookup for metadata (completed_at per task_id)
    completed_meta: dict[str, dict] = {item["task_id"]: item for item in completed_today}

    # ------------------------------------------------------------------
    # 3. Upsert dimensions (SCD Type 2)
    # ------------------------------------------------------------------
    conn = get_conn()
    try:
        for task in regular:
            row = _build_task_dim_row(task, projects, sections)
            deadline_obj = task.get("deadline")
            row["deadline"] = _parse_date(deadline_obj.get("date") if deadline_obj else None)
            row["duration_minutes"] = _parse_duration_minutes(task.get("duration"))
            upsert_task_dimension(conn, _T_TASKS, "regular", row, now_ts)

        for task in recurring:
            row = _build_task_dim_row(task, projects, sections)
            due = task.get("due") or {}
            row["recurrence_string"] = due.get("string") or None
            upsert_task_dimension(conn, _T_REC_TASKS, "recurring", row, now_ts)

        log.info(
            "dimensions upserted",
            extra={"regular": len(regular), "recurring": len(recurring)},
        )

        # ------------------------------------------------------------------
        # 4. Build non-recurring snapshot facts
        # ------------------------------------------------------------------
        snapshot_rows: list[dict] = []

        # 4a. Active regular tasks due today or overdue
        for task in regular:
            due = task.get("due") or {}
            due_date = _parse_date(due.get("date"))
            if due_date is None or due_date > today:
                continue  # undated or future — skip

            task_id = task["id"]
            was_completed = (task_id in completed_ids) if pro_plan else False
            completed_at = _parse_ts(completed_meta[task_id].get("completed_at")) if was_completed else None
            created_at = _parse_ts(task.get("created_at"))
            if was_completed and completed_at and created_at:
                days_open = (completed_at.date() - created_at.date()).days
            elif created_at:
                days_open = (today - created_at.date()).days
            else:
                days_open = None

            snapshot_rows.append(
                {
                    "snapshot_date": today,
                    "snapshotted_at": now_ts,
                    "task_id": task_id,
                    "due_date": due_date,
                    "was_completed": was_completed,
                    "completed_at": completed_at,
                    "days_open": days_open,
                }
            )

        # 4b. Completed-today items not present in active list (archived non-recurring)
        for item in completed_today:
            task_id = item["task_id"]
            if task_id in active_task_ids:
                continue  # recurring task still active — handled in recurring log

            completed_at = _parse_ts(item.get("completed_at"))
            due = item.get("due") or {}
            due_date = _parse_date(due.get("date"))
            created_at = _parse_ts(item.get("created_at"))
            if completed_at and created_at:
                days_open = (completed_at.date() - created_at.date()).days
            else:
                days_open = None

            snapshot_rows.append(
                {
                    "snapshot_date": today,
                    "snapshotted_at": now_ts,
                    "task_id": task_id,
                    "due_date": due_date,
                    "was_completed": True,
                    "completed_at": completed_at,
                    "days_open": days_open,
                }
            )

        # ------------------------------------------------------------------
        # 5. Build recurring log facts
        # ------------------------------------------------------------------
        recurring_rows: list[dict] = []

        for task in recurring:
            task_id = task["id"]
            due = task.get("due") or {}
            task_due_date = _parse_date(due.get("date"))

            if pro_plan:
                was_completed = task_id in completed_ids
                if was_completed:
                    completed_at = _parse_ts(completed_meta[task_id].get("completed_at"))
                    completion_signal = "completed_api"
                else:
                    completed_at = None
                    completion_signal = None
            else:
                # Due-date shift heuristic: if due date already moved past today,
                # the task was completed at some point today.
                was_completed = task_due_date is not None and task_due_date > today
                completed_at = None
                completion_signal = "due_date_shift" if was_completed else None

            # Only log tasks that were due today or were completed today.
            if not was_completed and (task_due_date is None or task_due_date > today):
                continue  # future task, not relevant to today

            recurring_rows.append(
                {
                    "log_date": today,
                    "snapshotted_at": now_ts,
                    "task_id": task_id,
                    "was_completed": was_completed,
                    "prev_due_date": today,
                    "next_due_date": task_due_date,
                    "completed_at": completed_at,
                    "completion_signal": completion_signal,
                }
            )

        # ------------------------------------------------------------------
        # 6. Write facts + commit in one transaction
        # ------------------------------------------------------------------
        insert_snapshot_facts(conn, snapshot_rows, _T_SNAPSHOT)
        insert_recurring_facts(conn, recurring_rows, _T_REC_LOG)
        conn.commit()

        completions = sum(1 for r in snapshot_rows if r["was_completed"])
        recurring_completions = sum(1 for r in recurring_rows if r["was_completed"])
        log.info(
            "snapshot complete",
            extra={
                "snapshot_facts": len(snapshot_rows),
                "completions": completions,
                "recurring_facts": len(recurring_rows),
                "recurring_completions": recurring_completions,
            },
        )

    except Exception:
        conn.rollback()
        log.exception("snapshot failed — transaction rolled back")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
