"""Postgres layer — connection, SCD Type 2 dimension upserts, fact inserts."""

from urllib.parse import urlparse, urlunparse

import psycopg2

from the_main_quest.omniconf import config


def _test_dsn(dsn: str) -> str:
    """Return a DSN pointing at <dbname>_test instead of <dbname>."""
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=parsed.path.rstrip("/") + "_test"))

# Fields that, if changed, trigger a new SCD Type 2 version.
# Keyed by task kind ("regular" / "recurring"), not by the table name, so that
# callers can point at any table name (e.g. _test suffixed tables).
_CHANGE_FIELDS = {
    "regular": [
        "task_content",
        "task_description",
        "project_id",
        "project_name",
        "section_id",
        "section_name",
        "parent_task_id",
        "labels",
        "priority",
        "deadline",
        "duration_minutes",
    ],
    "recurring": [
        "task_content",
        "task_description",
        "project_id",
        "project_name",
        "section_id",
        "section_name",
        "parent_task_id",
        "labels",
        "priority",
        "recurrence_string",
    ],
}


def get_conn():
    dsn = config.postgres.main_quest.dsn
    if config.get("todoist_snapshot.use_test_db", False):
        dsn = _test_dsn(dsn)
    return psycopg2.connect(dsn)


# ---------------------------------------------------------------------------
# SCD Type 2 dimension upsert
# ---------------------------------------------------------------------------

def upsert_task_dimension(conn, table: str, kind: str, row: dict, now_ts) -> None:
    """
    SCD Type 2 upsert.

    table — actual SQL table name (may be a _test variant)
    kind  — "regular" or "recurring"; selects change-field set and INSERT shape

    - No open row          → INSERT first version.
    - Open row unchanged   → UPDATE last_seen_at only.
    - Open row changed     → close old (valid_to=now_ts), INSERT new row.
    """
    change_fields = _CHANGE_FIELDS[kind]

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(change_fields)} "
            f"FROM {table} "
            "WHERE task_id = %s AND valid_to IS NULL",
            (row["task_id"],),
        )
        existing = cur.fetchone()

        if existing is None:
            _insert_dimension_row(cur, table, kind, row, now_ts, now_ts)
            return

        new_vals = [row.get(f) for f in change_fields]
        if _vals_equal(list(existing), new_vals, change_fields):
            cur.execute(
                f"UPDATE {table} SET last_seen_at = %s "
                "WHERE task_id = %s AND valid_to IS NULL",
                (now_ts, row["task_id"]),
            )
        else:
            cur.execute(
                f"UPDATE {table} SET valid_to = %s "
                "WHERE task_id = %s AND valid_to IS NULL",
                (now_ts, row["task_id"]),
            )
            _insert_dimension_row(cur, table, kind, row, now_ts, now_ts)


def _vals_equal(existing: list, new: list, fields: list[str]) -> bool:
    for i, field in enumerate(fields):
        e, n = existing[i], new[i]
        if field == "labels":
            if sorted(e or []) != sorted(n or []):
                return False
        else:
            if e != n:
                return False
    return True


def _insert_dimension_row(cur, table: str, kind: str, row: dict, valid_from, last_seen_at) -> None:
    if kind == "regular":
        cur.execute(
            f"""
            INSERT INTO {table}
                (task_id, task_content, task_description,
                 project_id, project_name,
                 section_id, section_name,
                 parent_task_id, labels, priority,
                 deadline, duration_minutes,
                 created_at, valid_from, valid_to, last_seen_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            """,
            (
                row["task_id"],
                row["task_content"],
                row.get("task_description"),
                row.get("project_id"),
                row.get("project_name"),
                row.get("section_id"),
                row.get("section_name"),
                row.get("parent_task_id"),
                row.get("labels"),
                row.get("priority"),
                row.get("deadline"),
                row.get("duration_minutes"),
                row.get("created_at"),
                valid_from,
                last_seen_at,
            ),
        )
    else:  # recurring
        cur.execute(
            f"""
            INSERT INTO {table}
                (task_id, task_content, task_description,
                 project_id, project_name,
                 section_id, section_name,
                 parent_task_id, labels, priority,
                 recurrence_string,
                 created_at, valid_from, valid_to, last_seen_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            """,
            (
                row["task_id"],
                row["task_content"],
                row.get("task_description"),
                row.get("project_id"),
                row.get("project_name"),
                row.get("section_id"),
                row.get("section_name"),
                row.get("parent_task_id"),
                row.get("labels"),
                row.get("priority"),
                row.get("recurrence_string"),
                row.get("created_at"),
                valid_from,
                last_seen_at,
            ),
        )


# ---------------------------------------------------------------------------
# Fact inserts
# ---------------------------------------------------------------------------

def insert_snapshot_facts(conn, rows: list, table: str) -> None:
    """Bulk-insert into the given snapshot fact table; ON CONFLICT DO NOTHING."""
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                f"""
                INSERT INTO {table}
                    (snapshot_date, snapshotted_at, task_id,
                     due_date, was_completed, completed_at, days_open)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    row["snapshot_date"],
                    row["snapshotted_at"],
                    row["task_id"],
                    row.get("due_date"),
                    row["was_completed"],
                    row.get("completed_at"),
                    row.get("days_open"),
                ),
            )


def insert_recurring_facts(conn, rows: list, table: str) -> None:
    """Bulk-insert into the given recurring log table; ON CONFLICT DO NOTHING."""
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                f"""
                INSERT INTO {table}
                    (log_date, snapshotted_at, task_id,
                     was_completed, prev_due_date, next_due_date,
                     completed_at, completion_signal)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    row["log_date"],
                    row["snapshotted_at"],
                    row["task_id"],
                    row["was_completed"],
                    row.get("prev_due_date"),
                    row.get("next_due_date"),
                    row.get("completed_at"),
                    row.get("completion_signal"),
                ),
            )
