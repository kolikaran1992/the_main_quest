"""
Unit tests for the pure extraction helpers in todoist_snapshot.main.
No network calls.

The module-level FileHandler in main.py is replaced with a NullHandler
before import — NullHandler has a valid .level attribute so logging calls
from other modules (e.g. fetcher) don't break during the test session.
"""

import logging
from datetime import date, datetime
from unittest.mock import patch

with patch("logging.FileHandler", return_value=logging.NullHandler()):
    from the_main_quest.todoist_snapshot.main import (
        _build_task_dim_row,
        _parse_date,
        _parse_duration_minutes,
        _parse_ts,
    )


def test_parse_ts():
    dt = _parse_ts("2026-03-01T10:30:00.000000Z")
    assert isinstance(dt, datetime)
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 3, 1, 10)
    assert dt.tzinfo is not None
    assert _parse_ts(None) is None
    assert _parse_ts("") is None


def test_parse_date():
    assert _parse_date("2026-03-01") == date(2026, 3, 1)
    # Truncates datetime strings that appear in date fields
    assert _parse_date("2026-03-01T00:00:00Z") == date(2026, 3, 1)
    assert _parse_date(None) is None
    assert _parse_date("") is None


def test_parse_duration_minutes():
    assert _parse_duration_minutes({"amount": 30, "unit": "minute"}) == 30
    assert _parse_duration_minutes({"amount": 1, "unit": "day"}) == 1440
    assert _parse_duration_minutes({"amount": 2, "unit": "day"}) == 2880
    assert _parse_duration_minutes({"unit": "minute"}) is None  # missing amount
    assert _parse_duration_minutes(None) is None


def test_build_task_dim_row_full_task():
    task = {
        "id": "t1",
        "content": "Write tests",
        "description": "keep them minimal",
        "project_id": "p1",
        "section_id": "s1",
        "parent_id": "parent_x",
        "labels": ["work", "deep_focus"],
        "priority": 3,
        "created_at": "2026-01-15T08:00:00.000000Z",
    }
    row = _build_task_dim_row(task, {"p1": "Work"}, {"s1": "Backlog"})
    assert row["task_id"] == "t1"
    assert row["task_content"] == "Write tests"
    assert row["project_name"] == "Work"
    assert row["section_name"] == "Backlog"
    assert row["parent_task_id"] == "parent_x"
    assert row["labels"] == ["work", "deep_focus"]
    assert isinstance(row["created_at"], datetime)


def test_build_task_dim_row_minimal_task():
    row = _build_task_dim_row({"id": "t2", "content": "X"}, {}, {})
    assert row["task_id"] == "t2"
    assert row["task_description"] is None
    assert row["project_id"] is None
    assert row["project_name"] is None
    assert row["labels"] == []
    assert row["created_at"] is None
