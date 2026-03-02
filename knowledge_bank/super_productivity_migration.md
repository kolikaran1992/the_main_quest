# Super Productivity Migration Design

Migration from Todoist (free tier) to self-hosted Super Productivity.
Implementation happens on a separate git branch. Current `master` becomes `todoist` once SP is verified working.

---

## Why switch

| Limitation today (Todoist free) | SP gain |
|---|---|
| Non-recurring completions untrackable — completed tasks API is Pro-only | `doneOn` timestamp on every completed task, no restrictions |
| Recurring completions via due-date-shift heuristic | Direct — all instances share `repeatCfgId`, each has its own `doneOn` |
| `created_at` NULL for most tasks (Todoist not returning it) | `created` always present |
| No time tracking at any tier | `timeSpentOnDay: Map<date, ms>` per task, built-in |
| API polling with token management, rate limits, tier gates | Read local JSON file — no auth, no rate limits, no paywalls |

---

## Branch strategy

```
master          ← current Todoist pipeline (stays untouched during development)
sp              ← new SP pipeline (branch off master)
```

Once SP is verified working in production:
- rename `master` → `todoist`
- rename `sp` → `master`

Todoist and SP pipelines run in parallel during the transition period, writing to separate Postgres tables.

---

## Infrastructure

### Docker containers (on `karan_ubuntu`)

Both run with `docker run` (not docker-compose — see observability README note).
Both join the `observability_default` network for consistency.

**Super Productivity web app**
```bash
docker run -d \
  --name super_productivity \
  --restart unless-stopped \
  --network observability_default \
  -p 8484:80 \
  johannesjo/super-productivity:latest
```
- Stateless static file server — no data stored here
- Access at `http://karan_ubuntu:8484` from any browser on the LAN

**WebDAV sync server**
```bash
docker run -d \
  --name sp_webdav \
  --restart unless-stopped \
  --network observability_default \
  -p 8585:80 \
  -e AUTH_TYPE=Basic \
  -e USERNAME=<username> \
  -e PASSWORD=<password> \
  -v /mnt/seagate_hdd1/super_productivity/webdav:/var/lib/dav \
  bytemark/webdav
```
- SP data JSON lives at `/mnt/seagate_hdd1/super_productivity/webdav/data/` on disk
- All clients sync to `http://karan_ubuntu:8585`
- Pipeline reads the JSON files directly from disk — no WebDAV API needed

**Data path to create before running:**
```bash
mkdir -p /mnt/seagate_hdd1/super_productivity/webdav
```

**Ports used (verify against observability README before deploying):**
Currently unused as of design time: `8484`, `8585`.
Already taken: `80`, `2283`, `3000`, `3100`, `3306`, `4317`, `5432`, `5433`, `6333`, `6334`, `6379`, `8096`, `9000`, `9080`, `9090`.

### Client sync config (all three clients)
- Sync provider: **WebDAV**
- URL: `http://karan_ubuntu:8585`
- Username/password: same credentials set in the Docker run command
- Mac: use the SP **desktop app** (not browser) — filesystem-backed, not affected by cache clearing
- Android: SP Android app — verify sync indicator is green before closing
- Browser: `http://karan_ubuntu:8484` — secondary access only, data stored in IndexedDB (lost if cache cleared)

---

## SP usage conventions (pipeline depends on these)

**Priority** — SP has no native priority field. Use tags:
| Tag | Maps to |
|---|---|
| `p1` | priority 4 (Todoist urgent) |
| `p2` | priority 3 |
| `p3` | priority 2 |
| `p4` | priority 1 (Todoist normal) |

Pipeline reads `tagIds`, resolves tag names, extracts `p1`–`p4` as integer priority.

**Projects** — direct equivalent to Todoist projects. Use them the same way.

**Sections** — SP has no sections. Use additional tags for cross-cutting grouping instead.

**Recurring tasks** — SP creates instances when the app is opened. Open the app (any device) once per day to generate that day's instances.

**End of day** — run **Finish Day** before bed. This moves `isDone: true` tasks from `main.json` to `archive.json`. The pipeline reads both files so completions are always visible, but Finish Day keeps `main.json` clean and is worth doing intentionally.

---

## Data files the pipeline reads

SP stores all state in two JSON files (synced to the WebDAV data directory):

| File | Contains | Pipeline use |
|---|---|---|
| `main.json` | Active tasks + `isDone: true` tasks not yet archived | Primary source — always current |
| `archive.json` | All historically archived tasks (post Finish Day) | Historical completions |

Both files follow the `AppBaseData` NgRx entity store schema. Key shapes:

```typescript
// Task (in main.json → tasks.entities, archive.json → archivedTasks.entities)
{
  id: string
  title: string
  notes?: string                         // markdown description
  projectId: string | null
  tagIds: string[]
  parentId: string | null
  subTaskIds: string[]
  isDone: boolean
  doneOn: number | null                  // Unix ms timestamp — the key field
  created: number                        // Unix ms timestamp — always present
  timeEstimate: number                   // ms
  timeSpentOnDay: { [dateStr: string]: number }  // e.g. {"2026-03-02": 3600000}
  repeatCfgId: string | null             // links recurring instances to config
  dueDay?: string                        // "YYYY-MM-DD"
  dueWithTime?: number                   // Unix ms
  plannedAt?: number                     // Unix ms
}

// TaskRepeatCfg (in main.json → taskRepeatCfg.entities)
{
  id: string
  title: string
  projectId: string | null
  tagIds: string[]
  repeatCycle: "DAILY" | "WEEKLY" | "MONTHLY" | "YEARLY"
  repeatEvery: number
  monday: boolean ... sunday: boolean
  repeatFromCompletionDate: boolean
  defaultEstimate: number
  startDate: string
}

// Project (in main.json → project.entities)
{ id: string, title: string, ... }

// Tag (in main.json → tag.entities)
{ id: string, title: string, ... }
```

---

## Postgres schema (new tables — separate from Todoist tables)

All table names config-driven via `settings.toml`, same pattern as Todoist tables.

### `sp_tasks` — SCD Type 2 dimension (non-recurring)
```sql
CREATE TABLE IF NOT EXISTS sp_tasks (
    id               SERIAL PRIMARY KEY,
    task_id          TEXT        NOT NULL,
    task_content     TEXT        NOT NULL,
    task_description TEXT,
    project_id       TEXT,
    project_name     TEXT,
    parent_task_id   TEXT,
    tag_ids          TEXT[],
    tag_names        TEXT[],
    priority         SMALLINT,           -- derived from p1/p2/p3/p4 tags
    time_estimate_ms BIGINT,
    created_at       TIMESTAMPTZ,
    valid_from       TIMESTAMPTZ NOT NULL,
    valid_to         TIMESTAMPTZ,
    last_seen_at     TIMESTAMPTZ NOT NULL
);
```

### `sp_daily_snapshot` — fact (non-recurring)
```sql
CREATE TABLE IF NOT EXISTS sp_daily_snapshot (
    snapshot_date  DATE        NOT NULL,
    snapshotted_at TIMESTAMPTZ NOT NULL,
    task_id        TEXT        NOT NULL,
    due_date       DATE,
    was_completed  BOOLEAN     NOT NULL,
    done_on        TIMESTAMPTZ,          -- doneOn converted from Unix ms
    days_open      INTEGER,
    PRIMARY KEY (snapshot_date, task_id)
);
```

### `sp_recurring_tasks` — SCD Type 2 dimension (keyed on repeatCfgId)
```sql
CREATE TABLE IF NOT EXISTS sp_recurring_tasks (
    id                SERIAL PRIMARY KEY,
    repeat_cfg_id     TEXT        NOT NULL,   -- TaskRepeatCfg.id
    task_content      TEXT        NOT NULL,
    project_id        TEXT,
    project_name      TEXT,
    tag_ids           TEXT[],
    tag_names         TEXT[],
    priority          SMALLINT,
    repeat_cycle      TEXT,
    repeat_every      INTEGER,
    repeat_days       TEXT[],               -- ["monday","wednesday"] etc
    default_estimate  BIGINT,
    created_at        TIMESTAMPTZ,
    valid_from        TIMESTAMPTZ NOT NULL,
    valid_to          TIMESTAMPTZ,
    last_seen_at      TIMESTAMPTZ NOT NULL
);
```

### `sp_recurring_log` — fact (one row per recurring instance)
```sql
CREATE TABLE IF NOT EXISTS sp_recurring_log (
    log_date          DATE        NOT NULL,
    snapshotted_at    TIMESTAMPTZ NOT NULL,
    task_id           TEXT        NOT NULL,   -- the instance task id
    repeat_cfg_id     TEXT        NOT NULL,
    was_completed     BOOLEAN     NOT NULL,
    done_on           TIMESTAMPTZ,
    due_day           DATE,
    time_spent_ms     BIGINT,                -- sum of timeSpentOnDay for this instance
    PRIMARY KEY (log_date, task_id)
);
```

### `sp_time_log` — fact (no Todoist equivalent)
```sql
CREATE TABLE IF NOT EXISTS sp_time_log (
    log_date       DATE        NOT NULL,
    snapshotted_at TIMESTAMPTZ NOT NULL,
    task_id        TEXT        NOT NULL,
    time_spent_ms  BIGINT      NOT NULL,
    PRIMARY KEY (log_date, task_id)
);
```

---

## Pipeline design

### Event-driven trigger — why not a fixed cron

A fixed nightly cron (e.g. 00:05am) breaks on extended work days — if you run Finish Day at
1:30am, the pipeline already fired without that data and the next night's run would mis-date it.

Instead the pipeline is **triggered by Finish Day itself**: when you click Finish Day, SP syncs
to WebDAV, writing the data file on disk. A watcher on `karan_ubuntu` detects this and fires
the pipeline. No fixed time, no continuity gaps.

**Trigger mechanism: `inotifywait` + systemd service**

A systemd service on `karan_ubuntu` (runs as `limited_user`) watches the WebDAV data directory:

```bash
# /etc/systemd/system/sp_snapshot_watcher.service
[Unit]
Description=Super Productivity snapshot watcher
After=network.target

[Service]
User=limited_user
ExecStart=/home/limited_user/bin/sp_snapshot_watcher.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# /home/limited_user/bin/sp_snapshot_watcher.sh
#!/bin/bash
WATCH_DIR="/mnt/seagate_hdd1/super_productivity/webdav/data"
DEBOUNCE=180  # seconds — wait for WebDAV sync to fully settle

inotifywait -m -e close_write --format '%f' "$WATCH_DIR" | while read filename; do
    sleep $DEBOUNCE
    SECRETS_DIRECTORY=/home/limited_user/dev_secrets \
    ENV_FOR_DYNACONF=ubuntu \
    /home/limited_user/.local/bin/poetry -C /home/limited_user/Projects/the_main_quest \
        run python -m runs.sp_snapshot
done
```

The 3-minute debounce absorbs multiple close_write events during a single WebDAV sync.
`ON CONFLICT DO NOTHING` ensures a double-trigger on the same day is a safe no-op.

**Behaviour by scenario:**

| Scenario | Outcome |
|---|---|
| Normal day, Finish Day at 11pm | Triggers at 11:03pm — correct |
| Extended day, Finish Day at 1:30am | Triggers at 1:33am — correct, dates derived from `doneOn` |
| Finish Day not run | Pipeline never fires — no empty rows, Grafana shows gap = no work |
| Finish Day run twice same day | Second trigger is a no-op via `ON CONFLICT DO NOTHING` |
| Multi-day gap (holiday) | No triggers — Grafana handles missing days as gaps |

### Entry point (in `runs/`)

```
runs/sp_snapshot.py     ← single daily pipeline (handles both regular and recurring)
```

### Pipeline modules (in `the_main_quest/sp_snapshot/`)

```
the_main_quest/sp_snapshot/
├── reader.py    — reads main.json + archive.json, resolves tag/project/repeatCfg lookups
├── _helpers.py  — parse doneOn (Unix ms → datetime), timeSpentOnDay, priority from tags
├── regular.py   — run() for non-recurring tasks (dimensions + facts)
├── recurring.py — run() for recurring tasks (dimensions + facts)
└── db.py        — Postgres layer (SCD Type 2 + fact inserts for SP tables)
```

### Date derivation — `doneOn` per task, not pipeline run time

Pipeline run time is irrelevant to what date a task belongs to. Instead:

```python
DAY_BOUNDARY_HOUR = config.sp_snapshot.day_boundary_hour  # default: 4

def work_date(done_on_ts: datetime) -> date:
    """Return the work date a completion belongs to.
    Anything before DAY_BOUNDARY_HOUR is attributed to the previous calendar day
    so that extended days past midnight are logged correctly.
    """
    if done_on_ts.hour < DAY_BOUNDARY_HOUR:
        return (done_on_ts - timedelta(days=1)).date()
    return done_on_ts.date()
```

- Task completed at 11:45pm March 2nd → `log_date = 2026-03-02` ✓
- Task completed at 1:30am March 3rd → `log_date = 2026-03-02` ✓ (boundary = 4am)
- Task completed at 5:00am March 3rd → `log_date = 2026-03-03` ✓

For **active tasks** (not completed, no `doneOn`): use the pipeline trigger timestamp
with the same `work_date()` logic as the reference date for `snapshot_date`.

### `reader.py` responsibilities
1. Read the SP backup JSON from the WebDAV data path (verify exact filename after first sync)
2. Collect all tasks: active from `main.json` + `isDone: true` from `main.json` + archived from `archive.json`
3. Build lookup dicts: `projects: {id → name}`, `tags: {id → name}`, `repeatCfgs: {id → config}`
4. Log a warning if file `last_modified` is older than 2 hours (stale sync detection)

### Subtask handling
Each subtask has its own `task_id` and `parentId` pointing to the parent.
Subtasks appear as independent rows in dimension and fact tables, linked by `parentId`.
New subtasks created mid-day: first seen by the pipeline that night, SCD Type 2 inserts them as new.

### Loki log file
```
/tmp/loki_the_main_quest__sp_snapshot.log
```

---

## Failure modes and handling

| Failure | Impact | Handling |
|---|---|---|
| App not opened for a day | Recurring instances not created — no data for that day | Grafana SQLs handle gaps (missing day = no activity, not an error) |
| Finish Day not run | Pipeline never fires — no rows written for that day | Read both files as safety net; gap in Grafana signals missed Finish Day |
| Extended day past midnight | Tasks mis-dated if using run time | `work_date()` uses `doneOn` per task + `day_boundary_hour` — always correct |
| inotifywait watcher dies | Pipeline stops triggering | systemd `Restart=always` auto-recovers; check `systemctl status sp_snapshot_watcher` |
| WebDAV sync not settled (double close_write) | Pipeline fires mid-sync on partial data | 3-minute debounce + `DO NOTHING` idempotency makes second trigger a safe no-op |
| Sync conflict (two clients simultaneous) | Last-write-wins — minor data loss possible | Low probability with two clients; no programmatic fix |
| Browser cache cleared | Data loss if unsynced | Use Mac desktop app as primary, not browser |

---

## How to use SP (daily workflow)

> Add this as a section in README.md when implementing the `sp` branch.

**Morning**
1. Open SP on any device — this generates today's recurring task instances
2. Verify sync indicator is green (especially on Android)

**During the day**
- Tag tasks `p1`–`p4` for priority
- Use projects for top-level grouping; tags for everything else (no sections in SP)
- Track time by starting the timer on a task while working

**End of day**
1. Tick off completed tasks
2. Run **Finish Day** — review unfinished tasks, archive completed ones
3. Verify sync is green before closing the app

**If something looks wrong in Grafana**
- Check that WebDAV sync ran: `ls -la /mnt/seagate_hdd1/super_productivity/webdav/data/`
- Check watcher service: `systemctl status sp_snapshot_watcher`
- Check pipeline logs: `tail /tmp/loki_the_main_quest__sp_snapshot.log`

---

## Settings.toml additions (on `sp` branch)

```toml
[default.sp_snapshot]
use_test_db = true
tasks_table = "sp_tasks"
snapshot_table = "sp_daily_snapshot"
recurring_tasks_table = "sp_recurring_tasks"
recurring_log_table = "sp_recurring_log"
time_log_table = "sp_time_log"
webdav_data_path = "@jinja {{this.home_dir}}/Data/SP_MOCK/"   # Mac dev: mock data
day_boundary_hour = 4   # completions before 4am count as previous calendar day

[ubuntu.sp_snapshot]
webdav_data_path = "/mnt/seagate_hdd1/super_productivity/webdav/data/"
```

---

## Open questions (resolve during implementation)

1. **Exact filename** SP writes to WebDAV — verify after first sync (likely `super-productivity-backup.json` but confirm on disk)
2. **WebDAV credentials** — decide before running the `docker run` command
3. **SP version pinning** — pin the Docker image to a specific version tag to avoid breaking schema changes on auto-update
4. **`day_boundary_hour`** — confirm 4am cutoff works for your schedule or adjust
5. **inotifywait availability** — confirm `inotify-tools` is installed on `karan_ubuntu` (`apt install inotify-tools`)
