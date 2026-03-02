# the_main_quest

Personal data pipeline and analytics project. Snapshots Todoist tasks into Postgres nightly; feeds Grafana dashboards for habit tracking, completion rates, and overdue task analysis.

## Navigation for LLMs

| What you need | Where to look |
|---|---|
| Extend or modify the project | `the_main_quest/agent.md` — config, logging, DB layer, adding pipelines |
| Todoist API field shapes | `knowledge_bank/todoist_api_exploration.md` |
| Snapshot schema design and dashboard queries | `knowledge_bank/todoist_snapshot_basic.md` |
| DB schema (run once) | `migrations/todoist_snapshot_schema.sql` |

## Loki log paths (ubuntu)

| Job | Log file |
|---|---|
| Non-recurring snapshot | `/tmp/loki_the_main_quest__todoist_snapshot_regular.log` |
| Recurring snapshot | `/tmp/loki_the_main_quest__todoist_snapshot_recurring.log` |

Query in Grafana: `{job="loki", project="todoist_snapshot_regular"} | json`

## Quick start

```bash
poetry install

# Non-recurring snapshot (test DB by default)
poetry run python -m runs.todoist_snapshot_regular

# Recurring snapshot (test DB by default)
poetry run python -m runs.todoist_snapshot_recurring

# Print pending tasks (used by OpenCode skill)
poetry run python -m runs.fetch_pending_tasks
```
