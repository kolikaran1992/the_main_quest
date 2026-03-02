"""Non-recurring task snapshot pipeline."""

import logging
import sys
from datetime import datetime

import pytz

from the_main_quest.omniconf import add_loki_handler, config
from the_main_quest.omniconf import logger as _base_logger

from .db import get_conn, insert_snapshot_facts, upsert_task_dimension
from .fetcher import fetch_active_tasks, fetch_completed_today, fetch_projects, fetch_sections
from ._helpers import _build_task_dim_row, _parse_date, _parse_duration_minutes, _parse_ts

add_loki_handler("todoist_snapshot_regular")

log = logging.LoggerAdapter(_base_logger, {"project": "todoist_snapshot_regular"})

_T_TASKS = config.todoist_snapshot.tasks_table
_T_SNAPSHOT = config.todoist_snapshot.snapshot_table


def run() -> None:
    tz = pytz.timezone(config.tz)
    now_ts = datetime.now(tz)
    today = now_ts.date()

    log.info("todoist_snapshot_regular starting", extra={"snapshot_date": today.isoformat()})

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
    # 2. Partition
    # ------------------------------------------------------------------
    regular = [t for t in active_tasks if not (t.get("due") or {}).get("is_recurring")]
    active_task_ids = {t["id"] for t in active_tasks}

    completed_ids: set[str] = {item["task_id"] for item in completed_today} if pro_plan else set()
    completed_meta: dict[str, dict] = {item["task_id"]: item for item in completed_today}

    # ------------------------------------------------------------------
    # 3. Upsert regular dimensions (SCD Type 2)
    # ------------------------------------------------------------------
    conn = get_conn()
    try:
        for task in regular:
            row = _build_task_dim_row(task, projects, sections)
            deadline_obj = task.get("deadline")
            row["deadline"] = _parse_date(deadline_obj.get("date") if deadline_obj else None)
            row["duration_minutes"] = _parse_duration_minutes(task.get("duration"))
            upsert_task_dimension(conn, _T_TASKS, "regular", row, now_ts)

        log.info("dimensions upserted", extra={"regular": len(regular)})

        # ------------------------------------------------------------------
        # 4. Build snapshot facts
        # ------------------------------------------------------------------
        snapshot_rows: list[dict] = []

        # 4a. Active regular tasks due today or overdue
        for task in regular:
            due = task.get("due") or {}
            due_date = _parse_date(due.get("date"))
            if due_date is None or due_date > today:
                continue

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
                continue  # still active (recurring or regular) — skip

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
        # 5. Commit
        # ------------------------------------------------------------------
        insert_snapshot_facts(conn, snapshot_rows, _T_SNAPSHOT)
        conn.commit()

        completions = sum(1 for r in snapshot_rows if r["was_completed"])
        log.info(
            "snapshot complete",
            extra={"snapshot_facts": len(snapshot_rows), "completions": completions},
        )

    except Exception:
        conn.rollback()
        log.exception("snapshot failed — transaction rolled back")
        raise
    finally:
        conn.close()
