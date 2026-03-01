-- Todoist Snapshot Schema
-- Run once against the target Postgres instance.
-- All statements use IF NOT EXISTS so they are safe to re-run.

-- ---------------------------------------------------------------------------
-- Non-recurring dimension (SCD Type 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS todoist_tasks (
    id               SERIAL PRIMARY KEY,
    task_id          TEXT        NOT NULL,
    task_content     TEXT        NOT NULL,
    task_description TEXT,
    project_id       TEXT,
    project_name     TEXT,
    section_id       TEXT,
    section_name     TEXT,
    parent_task_id   TEXT,
    labels           TEXT[],
    priority         SMALLINT,
    deadline         DATE,
    duration_minutes INTEGER,
    created_at       TIMESTAMPTZ,
    valid_from       TIMESTAMPTZ NOT NULL,
    valid_to         TIMESTAMPTZ,
    last_seen_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_todoist_tasks_task_id
    ON todoist_tasks (task_id);

CREATE INDEX IF NOT EXISTS idx_todoist_tasks_task_id_open
    ON todoist_tasks (task_id)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_todoist_tasks_labels
    ON todoist_tasks USING GIN (labels);

-- ---------------------------------------------------------------------------
-- Non-recurring fact (append-only, one row per snapshot_date + task_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS todoist_daily_snapshot (
    snapshot_date  DATE        NOT NULL,
    snapshotted_at TIMESTAMPTZ NOT NULL,
    task_id        TEXT        NOT NULL,
    due_date       DATE,
    was_completed  BOOLEAN     NOT NULL,
    completed_at   TIMESTAMPTZ,
    days_open      INTEGER,
    PRIMARY KEY (snapshot_date, task_id)
);

CREATE INDEX IF NOT EXISTS idx_todoist_daily_snapshot_date
    ON todoist_daily_snapshot (snapshot_date);

-- ---------------------------------------------------------------------------
-- Recurring dimension (SCD Type 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS todoist_recurring_tasks (
    id                SERIAL PRIMARY KEY,
    task_id           TEXT        NOT NULL,
    task_content      TEXT        NOT NULL,
    task_description  TEXT,
    project_id        TEXT,
    project_name      TEXT,
    section_id        TEXT,
    section_name      TEXT,
    parent_task_id    TEXT,
    labels            TEXT[],
    priority          SMALLINT,
    recurrence_string TEXT,
    created_at        TIMESTAMPTZ,
    valid_from        TIMESTAMPTZ NOT NULL,
    valid_to          TIMESTAMPTZ,
    last_seen_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_todoist_recurring_tasks_task_id
    ON todoist_recurring_tasks (task_id);

CREATE INDEX IF NOT EXISTS idx_todoist_recurring_tasks_task_id_open
    ON todoist_recurring_tasks (task_id)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_todoist_recurring_tasks_labels
    ON todoist_recurring_tasks USING GIN (labels);

-- ---------------------------------------------------------------------------
-- Recurring fact (append-only, one row per log_date + task_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS todoist_recurring_log (
    log_date          DATE        NOT NULL,
    snapshotted_at    TIMESTAMPTZ NOT NULL,
    task_id           TEXT        NOT NULL,
    was_completed     BOOLEAN     NOT NULL,
    prev_due_date     DATE,
    next_due_date     DATE,
    completed_at      TIMESTAMPTZ,
    completion_signal TEXT,
    PRIMARY KEY (log_date, task_id)
);

CREATE INDEX IF NOT EXISTS idx_todoist_recurring_log_date
    ON todoist_recurring_log (log_date);

CREATE INDEX IF NOT EXISTS idx_todoist_recurring_log_task_id
    ON todoist_recurring_log (task_id);
