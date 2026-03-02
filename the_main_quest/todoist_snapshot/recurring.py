"""Recurring task snapshot pipeline."""

import logging
import sys
from datetime import datetime

import pytz

from the_main_quest.omniconf import add_loki_handler, config
from the_main_quest.omniconf import logger as _base_logger

from .db import get_conn, insert_recurring_facts, upsert_task_dimension
from .fetcher import fetch_active_tasks, fetch_completed_today, fetch_projects, fetch_sections
from ._helpers import _build_task_dim_row, _parse_date, _parse_ts

add_loki_handler("todoist_snapshot_recurring")

log = logging.LoggerAdapter(_base_logger, {"project": "todoist_snapshot_recurring"})

_T_REC_TASKS = config.todoist_snapshot.recurring_tasks_table
_T_REC_LOG = config.todoist_snapshot.recurring_log_table


def run() -> None:
    tz = pytz.timezone(config.tz)
    now_ts = datetime.now(tz)
    today = now_ts.date()

    log.info("todoist_snapshot_recurring starting", extra={"snapshot_date": today.isoformat()})

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
    recurring = [t for t in active_tasks if (t.get("due") or {}).get("is_recurring")]

    completed_ids: set[str] = {item["task_id"] for item in completed_today} if pro_plan else set()
    completed_meta: dict[str, dict] = {item["task_id"]: item for item in completed_today}

    # ------------------------------------------------------------------
    # 3. Upsert recurring dimensions (SCD Type 2)
    # ------------------------------------------------------------------
    conn = get_conn()
    try:
        for task in recurring:
            row = _build_task_dim_row(task, projects, sections)
            due = task.get("due") or {}
            row["recurrence_string"] = due.get("string") or None
            upsert_task_dimension(conn, _T_REC_TASKS, "recurring", row, now_ts)

        log.info("dimensions upserted", extra={"recurring": len(recurring)})

        # ------------------------------------------------------------------
        # 4. Build recurring log facts
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
                continue

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
        # 5. Commit
        # ------------------------------------------------------------------
        insert_recurring_facts(conn, recurring_rows, _T_REC_LOG)
        conn.commit()

        recurring_completions = sum(1 for r in recurring_rows if r["was_completed"])
        log.info(
            "snapshot complete",
            extra={
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
