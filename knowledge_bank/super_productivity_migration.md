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

### Entry points (in `runs/`)

```
runs/sp_snapshot_regular.py     ← non-recurring pipeline
runs/sp_snapshot_recurring.py   ← recurring pipeline
```

### Pipeline modules (in `the_main_quest/sp_snapshot/`)

```
the_main_quest/sp_snapshot/
├── reader.py       — reads + merges main.json and archive.json, resolves tag/project names
├── _helpers.py     — parse doneOn (Unix ms → datetime), timeSpentOnDay, priority from tags
├── regular.py      — run() for non-recurring pipeline
├── recurring.py    — run() for recurring pipeline
└── db.py           — Postgres layer (SCD Type 2 + fact inserts for SP tables)
```

### `reader.py` responsibilities
1. Read the SP backup JSON from the WebDAV data path (verify exact filename after first sync)
2. Merge active tasks from `main.json` + `isDone: true` tasks + archived tasks from `archive.json`
3. Build lookup dicts: `projects: {id → name}`, `tags: {id → name}`, `repeatCfgs: {id → config}`
4. Log a warning if file `last_modified` is older than 2 hours (stale sync detection)

### Cron schedule (on `limited_user@karan_ubuntu`)

```
# SP non-recurring snapshot — every hour
0 * * * * SECRETS_DIRECTORY=... ENV_FOR_DYNACONF=ubuntu poetry -C .../the_main_quest run python -m runs.sp_snapshot_regular

# SP recurring snapshot — nightly at 23:55 IST (18:25 UTC)
25 18 * * * SECRETS_DIRECTORY=... ENV_FOR_DYNACONF=ubuntu poetry -C .../the_main_quest run python -m runs.sp_snapshot_recurring
```

### Loki log files
```
/tmp/loki_the_main_quest__sp_snapshot_regular.log
/tmp/loki_the_main_quest__sp_snapshot_recurring.log
```

---

## Failure modes and handling

| Failure | Impact | Handling |
|---|---|---|
| App not opened for a day | Recurring instances not created — no data for that day | Grafana SQLs handle gaps (missing day = no activity, not an error) |
| Finish Day not run | Completions in `main.json` not yet in `archive.json` | Pipeline reads both files — always visible |
| WebDAV sync stale | Pipeline reads old data | Log warning if file `last_modified` > 2h; `snapshotted_at` in Grafana reveals it |
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
- Check pipeline logs: `tail /tmp/loki_the_main_quest__sp_snapshot_regular.log`

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

[ubuntu.sp_snapshot]
webdav_data_path = "/mnt/seagate_hdd1/super_productivity/webdav/data/"
```

---

## Open questions (resolve during implementation)

1. **Exact filename** SP writes to WebDAV — verify after first sync (likely `super-productivity-backup.json` but confirm on disk)
2. **WebDAV credentials** — decide before running the `docker run` command
3. **SP version pinning** — pin the Docker image to a specific version tag to avoid breaking schema changes on auto-update
