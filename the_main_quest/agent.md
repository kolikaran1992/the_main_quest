# Agent Guide — the_main_quest

Instructions for AI agents extending or modifying this project.

---

## Project structure

```
the_main_quest/
├── pyproject.toml                        # Poetry deps; no poetry.lock in git
├── opencode.json                         # Project-level OpenCode config
├── migrations/
│   └── todoist_snapshot_schema.sql       # Run once via runs/setup_postgres.py
├── runs/                                 # One-off and utility scripts
│   ├── setup_postgres.py                 # Creates role, DBs, applies schema
│   └── fetch_pending_tasks.py            # Prints non-recurring pending tasks (stdout)
├── tests/
│   └── todoist_fetch/
│       ├── test_fetcher.py               # Real-API integration tests
│       └── test_extraction.py            # Pure unit tests for extraction helpers
├── knowledge_bank/
│   ├── todoist_api_exploration.md        # Todoist REST v1 field reference
│   └── todoist_snapshot_basic.md        # Full snapshot design spec
├── .opencode/skills/pending-tasks/
│   └── SKILL.md                         # OpenCode skill: runs fetch_pending_tasks
└── the_main_quest/
    ├── omniconf.py                       # Dynaconf config + logger (import from here)
    ├── settings_file/
    │   └── settings.toml                # Config defaults and table names
    └── todoist_snapshot/
        ├── fetcher.py                   # Todoist REST API layer
        ├── db.py                        # Postgres layer (SCD Type 2, fact inserts)
        └── main.py                      # Orchestrator — this is the nightly cron entry
```

---

## Config system

All config lives in `the_main_quest/omniconf.py`. Import from there everywhere:

```python
from the_main_quest.omniconf import config, logger
```

**Settings files** (merged in order):
1. `the_main_quest/settings_file/settings.toml` — defaults committed to git
2. Any extra `*.toml` files in `settings_file/` (committed, non-secret)
3. All `*.toml` files in `SECRETS_DIRECTORY` env var — secrets, never committed

**Environments** (`ENV_FOR_DYNACONF`):
- unset / `default` — Mac development
- `ubuntu` — remote server (`limited_user@192.168.1.50`)
- `admin` — used only by `runs/setup_postgres.py`

**Key config paths:**

| Key | Where set | Notes |
|---|---|---|
| `config.postgres.main_quest.dsn` | secrets TOML `[default/ubuntu.postgres.main_quest]` | App DB connection |
| `config.todoist.api_token` | secrets TOML | Never log |
| `config.todoist_snapshot.use_test_db` | `settings.toml` | `true` on Mac, `false` on ubuntu |
| `config.todoist_snapshot.tasks_table` | `settings.toml` | SQL table name |
| `config.todoist_snapshot.snapshot_table` | `settings.toml` | SQL table name |
| `config.todoist_snapshot.recurring_tasks_table` | `settings.toml` | SQL table name |
| `config.todoist_snapshot.recurring_log_table` | `settings.toml` | SQL table name |

Table names are config-driven — never hardcode SQL table names in Python.

---

## Postgres / DB layer

**Test DB**: `db.get_conn()` appends `_test` to the DSN database name when `use_test_db=true`. The test database (`main_quest_test`) has the identical schema. Set `use_test_db = false` in `settings.toml` (or override via env) for production runs.

**SCD Type 2 upsert** (`db.upsert_task_dimension`):
- Pass `kind="regular"` or `kind="recurring"` — this selects the change-field set and INSERT shape
- `table` is the actual SQL name (from config) — decoupled from `kind`

**Fact inserts** (`insert_snapshot_facts`, `insert_recurring_facts`):
- Append-only, `ON CONFLICT DO NOTHING`
- Pass `table` explicitly

---

## Loki logging

Use `add_loki_handler(suffix)` for all jobs. The log path is environment-driven:

| Env | `loki_log_path` | Result |
|---|---|---|
| `default` (Mac) | `~/Data/THE_MAIN_QUEST/logs/` | Local file, Promtail ignores it — test runs stay out of Loki |
| `ubuntu` | `/tmp/` | `/tmp/loki_the_main_quest__<suffix>.log` — picked up by Promtail catch-all |

```python
import logging
from the_main_quest.omniconf import add_loki_handler, logger as _base_logger

add_loki_handler("myjob")
log = logging.LoggerAdapter(_base_logger, {"project": "myjob"})
```

Query in Grafana: `{job="loki", project="myjob"} | json`

Loki rejects log entries older than 7 days. Never write historical timestamps to log lines.

---

## Adding a new pipeline

1. Create a subpackage under `the_main_quest/<name>/`
2. Add config keys under `[default.<name>]` in `settings.toml`
3. Add secrets (if any) to the secrets TOML template and document in `postgres.toml.template`
4. Add a Loki-compatible `FileHandler` as shown above
5. Add tests under `tests/<name>/`
6. Add a cron entry on `limited_user@192.168.1.50` pointing at `python -m the_main_quest.<name>.main`

---

## Running scripts

```bash
# One-time DB setup (run as admin, reads from [admin.postgres] in secrets TOML)
poetry run python -m runs.setup_postgres

# Nightly snapshot (runs locally against test DB by default)
poetry run python -m the_main_quest.todoist_snapshot.main

# Print pending non-recurring tasks (used by OpenCode pending-tasks skill)
poetry run python -m runs.fetch_pending_tasks

# Tests
poetry run pytest tests/
```

