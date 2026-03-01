# Todoist Daily Snapshot — Design

## Purpose
Nightly snapshot (11:55 PM) of Todoist task status → Postgres → Grafana. Tracks
daily completion, effort by project/label, overdue carry-forward, and long-term
expertise/cookie-jar retrospectives.

## Capture logic
- **Active tasks with `due_date ≤ today`** → `was_completed = false`
  (overdue/pending)
- **Tasks completed today** → `was_completed = true` (regardless of due date)
- **Undated tasks** → only captured when completed (never penalised as overdue)
- **Dimension reconciliation — SCD Type 2 (every run):** fetch all active tasks
  and compare each against the current open version (`valid_to IS NULL`) using
  `task_id`. If metadata is unchanged, only update `last_seen_at`. If any field
  changed (section, project, content, priority, etc.), close the old row by
  setting `valid_to = NOW()` and insert a new row with `valid_from = NOW()`.
  Tasks no longer returned by the API (completed, deleted) are not touched —
  their open row stays with a stale `last_seen_at`. Fact tables reference
  `task_id`; dashboard queries join on the version whose `valid_from`/`valid_to`
  window covers the snapshot date.
- **Subtasks with a due date but undated parent** → captured normally; the
  parent's missing due date does not propagate. The `parent_task_id` FK links
  them but each task is evaluated independently for overdue/completion.
- **Recurring tasks (completion detection):** at snapshot time (11:55 PM), if a
  recurring task has `due.date > today`, it was completed today — the due date
  shifted forward to the next occurrence. Record `prev_due_date = today` (the
  instance that was completed) and `completion_signal = 'due_date_shift'`.
  Secondary corroborating signal: `updated_at ≠ added_at`.
  If the completed REST endpoint is accessible (Pro plan), prefer
  `completion_signal = 'completed_api'` and use the API `completed_at` directly.

## Tables

Non-recurring and recurring tasks are separated at both the dimension and fact
level. Their completion semantics and dashboard use cases are different enough
to warrant separate tables. Both tables stay generic — no task-specific fields.

---

### Non-recurring

#### `todoist_tasks` — dimension (SCD Type 2)
One row per version of a non-recurring task. Multiple rows per `task_id` when
metadata has changed historically.

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | Surrogate key |
| `task_id` | text | Todoist task ID — not unique; use with `valid_to IS NULL` for current |
| `task_content` | text | Task title |
| `task_description` | text | Body/notes |
| `project_id` | text | |
| `project_name` | text | |
| `section_id` | text | |
| `section_name` | text | |
| `parent_task_id` | text | Populated if subtask |
| `labels` | text[] | Tag with domain areas for expertise tracking |
| `priority` | smallint | 1=normal 2=medium 3=high 4=urgent |
| `deadline` | date | Hard deadline if set; NULL otherwise |
| `duration_minutes` | integer | Time-box estimate if set; NULL otherwise |
| `created_at` | timestamptz | When task was created in Todoist |
| `valid_from` | timestamptz | When this version was first observed |
| `valid_to` | timestamptz | When this version was superseded; NULL = current version |
| `last_seen_at` | timestamptz | Updated every run; stale = task gone from API |

```sql
CREATE INDEX ON todoist_tasks (task_id);
CREATE INDEX ON todoist_tasks (task_id) WHERE valid_to IS NULL;
```

#### `todoist_daily_snapshot` — fact (append-only)
One row per `(snapshot_date, task_id)`. Lean — no text, just outcome.

| Column | Type | Notes |
|---|---|---|
| `snapshot_date` | date PK | |
| `snapshotted_at` | timestamptz | |
| `task_id` | text PK → FK `todoist_tasks` | |
| `due_date` | date | NULL for undated completions |
| `was_completed` | boolean | |
| `completed_at` | timestamptz | NULL if not completed |
| `days_open` | integer | `completed_at - created_at` or `snapshot_date - created_at` |

```sql
CREATE INDEX ON todoist_daily_snapshot (snapshot_date);
CREATE INDEX ON todoist_tasks USING GIN (labels);
```

---

### Recurring

#### `todoist_recurring_tasks` — dimension (SCD Type 2)
One row per version of a recurring task. Multiple rows per `task_id` when
metadata has changed historically.

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | Surrogate key |
| `task_id` | text | Todoist task ID — not unique; use with `valid_to IS NULL` for current |
| `task_content` | text | Task title |
| `task_description` | text | |
| `project_id` | text | |
| `project_name` | text | |
| `section_id` | text | |
| `section_name` | text | |
| `parent_task_id` | text | |
| `labels` | text[] | |
| `priority` | smallint | 1=normal 2=medium 3=high 4=urgent |
| `recurrence_string` | text | Raw API value e.g. `"every day"`, `"every week"` |
| `created_at` | timestamptz | When task was created in Todoist |
| `valid_from` | timestamptz | When this version was first observed |
| `valid_to` | timestamptz | When this version was superseded; NULL = current version |
| `last_seen_at` | timestamptz | Updated every run; stale = task gone from API |

```sql
CREATE INDEX ON todoist_recurring_tasks (task_id);
CREATE INDEX ON todoist_recurring_tasks (task_id) WHERE valid_to IS NULL;
```

#### `todoist_recurring_log` — fact (append-only)
One row per `(log_date, task_id)`. Records each instance outcome.

| Column | Type | Notes |
|---|---|---|
| `log_date` | date PK | The date the task instance was due (today at snapshot time) |
| `snapshotted_at` | timestamptz | |
| `task_id` | text PK → FK `todoist_recurring_tasks` | |
| `was_completed` | boolean | |
| `prev_due_date` | date | Due date before the shift; equals `log_date` on completion |
| `next_due_date` | date | `due.date` from API after completion (the rescheduled date) |
| `completed_at` | timestamptz | From API when Pro plan available; else NULL |
| `completion_signal` | text | `'due_date_shift'` \| `'completed_api'` \| NULL (missed) |

```sql
CREATE INDEX ON todoist_recurring_log (log_date);
CREATE INDEX ON todoist_recurring_log (task_id);
CREATE INDEX ON todoist_recurring_tasks USING GIN (labels);
```

## Data sources
- Active tasks: `GET https://api.todoist.com/api/v1/tasks` (cursor-paginated)
- Completed tasks: `GET https://api.todoist.com/api/v1/tasks/completed/by_completion_date`
  (Pro plan only — 403 on free; fall back to due-date shift detection)
- Project/section names: `GET /api/v1/projects`, `GET /api/v1/sections` → build lookup maps
- Recurring completion detection (free plan fallback): compare `due.date > today`
  at snapshot time; corroborate with `updated_at ≠ added_at`

## Key Grafana queries

**Daily completion rate**
```sql
SELECT s.snapshot_date,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.was_completed) / COUNT(*), 1) AS pct
FROM todoist_daily_snapshot s
WHERE s.due_date <= s.snapshot_date
GROUP BY 1
```

**Effort by label per week (cookie jar)**
```sql
SELECT DATE_TRUNC('week', s.snapshot_date) AS week,
       UNNEST(t.labels) AS area, COUNT(*) AS completed
FROM todoist_daily_snapshot s
JOIN todoist_tasks t ON t.task_id = s.task_id
    AND s.snapshotted_at BETWEEN t.valid_from AND COALESCE(t.valid_to, 'infinity')
WHERE s.was_completed = true
GROUP BY 1, 2
```

**Overdue tasks**
```sql
SELECT t.task_content, t.project_name, s.due_date,
       s.snapshot_date - s.due_date AS days_overdue
FROM todoist_daily_snapshot s
JOIN todoist_tasks t ON t.task_id = s.task_id
    AND s.snapshotted_at BETWEEN t.valid_from AND COALESCE(t.valid_to, 'infinity')
WHERE s.was_completed = false AND s.due_date < s.snapshot_date
ORDER BY days_overdue DESC
```

**Recurring task adherence rate (30-day rolling)**
```sql
SELECT t.task_content, t.section_name, t.project_name,
       ROUND(100.0 * COUNT(*) FILTER (WHERE l.was_completed) / COUNT(*), 1) AS adherence_pct
FROM todoist_recurring_log l
JOIN todoist_recurring_tasks t ON t.task_id = l.task_id
    AND l.snapshotted_at BETWEEN t.valid_from AND COALESCE(t.valid_to, 'infinity')
WHERE l.log_date >= CURRENT_DATE - 30
GROUP BY t.task_content, t.section_name, t.project_name
ORDER BY adherence_pct
```

**Current streak per recurring task**
```sql
WITH ordered AS (
    SELECT task_id, log_date, was_completed,
           ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY log_date DESC) AS rn
    FROM todoist_recurring_log
),
streak AS (
    SELECT task_id, COUNT(*) AS streak_days
    FROM ordered
    WHERE was_completed = true
      AND rn = ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY rn)
    GROUP BY task_id
)
SELECT t.task_content, t.section_name, COALESCE(s.streak_days, 0) AS streak_days
FROM todoist_recurring_tasks t
LEFT JOIN streak s USING (task_id)
WHERE t.valid_to IS NULL
ORDER BY streak_days DESC
```

**Completion heatmap (task × day)**
```sql
SELECT l.log_date, t.task_content, l.was_completed::int AS completed
FROM todoist_recurring_log l
JOIN todoist_recurring_tasks t ON t.task_id = l.task_id
    AND l.snapshotted_at BETWEEN t.valid_from AND COALESCE(t.valid_to, 'infinity')
WHERE l.log_date >= CURRENT_DATE - 90
ORDER BY t.task_content, l.log_date
```

**Missed recurring tasks today**
```sql
SELECT t.task_content, t.project_name, t.section_name, t.recurrence_string
FROM todoist_recurring_log l
JOIN todoist_recurring_tasks t ON t.task_id = l.task_id
    AND l.snapshotted_at BETWEEN t.valid_from AND COALESCE(t.valid_to, 'infinity')
WHERE l.log_date = CURRENT_DATE AND l.was_completed = false
ORDER BY t.project_name, t.section_name
```

## Known failure modes

**Operational — most relevant to the 11:55 PM cron**
- **Mid-run crash:** no transaction wraps the full run. If it crashes between the
  dimension phase and the fact phase, dimension rows are updated with no
  corresponding fact rows written. Stale artifacts are indistinguishable from a
  clean run.
- **Dimension must be reconciled before facts:** if a task's metadata changed and
  the run crashes before the SCD close/insert completes, `snapshotted_at` falls
  outside all version windows and the dimension join returns nothing for that row.
- **Changes after 11:55 PM:** any completion, section move, or edit between
  11:55 PM and midnight is missed entirely and not reflected until the next night.
- **Missed run:** no snapshot or recurring log rows for that date. The gap is
  silent — the dashboard shows nothing rather than a recorded miss.

**Data quality**
- **Absent recurring rows inflate adherence:** a missed run produces no
  `was_completed = false` entry — the date is simply absent. Since the adherence
  query uses `COUNT(*)` as the denominator, missed runs silently inflate the rate.
- **False positive recurring completion:** manually rescheduling a recurring task
  (without completing it) shifts `due.date` forward and is indistinguishable from
  a real completion. A new recurring task created today with a future due date
  has the same signature.
- **Recurring ↔ non-recurring type change:** if a task's recurrence is added or
  removed, it needs to migrate between the two dimension/fact table pairs. Not
  handled — rows strand in the wrong table.

**Schema**
- **FK not enforceable:** `task_id` in fact tables cannot carry a real Postgres FK
  since `task_id` is not unique in SCD Type 2 dimension tables. It is a logical
  reference only — no referential integrity at DB level.
- **Streak query invalid:** the current streak query uses a window function inside
  a `WHERE` clause, which Postgres does not allow. It will error at runtime and
  needs a gaps-and-islands rewrite.

## Infrastructure
- Script runs on `limited_user@192.168.1.50` via cron: `55 23 * * *`
- Postgres: TBD — confirm instance/db/user before implementation
- Todoist API token: env var `TODOIST_API_TOKEN`
- Dependencies: `requests`, `psycopg2`
- Logging: `/tmp/loki_todoist_snapshot.log` (JSON lines,
  `"project": "todoist_snapshot"`)



