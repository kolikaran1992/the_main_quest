# Todoist API v1 — Exploration Guide

Use this guide in a fresh session to verify what is actually accessible before finalising the
snapshot design. Run every snippet with `poetry run python -c "..."` from the project root.

**⚠️ NEVER print, log, or include `config.todoist.api_token` in any output.**
Use `bool(config.todoist.api_token)` to check presence, `len(...)` to check length — never the value itself.

---

## Authentication

Token lives at `config.todoist.api_token` (loaded from `SECRETS_DIRECTORY`).
Verify it is loaded (without revealing it):
```python
from the_main_quest.omniconf import config
tok = config.todoist.api_token
print("token present:", bool(tok))
print("token len:", len(str(tok)))   # should be 40
```

All requests use `Authorization: Bearer <token>`. A helper already exists:
```python
from the_main_quest.todoist_snapshot.fetcher import _headers
# DO NOT print _headers() — it contains the token
# Instead, just call it and pass it to requests; never print it
```

---

## Base URLs

| API | Base URL |
|---|---|
| REST v1 (current) | `https://api.todoist.com/api/v1` |
| Sync v1 (current) | `https://api.todoist.com/api/v1/sync` |
| REST v2 (deprecated, 410) | `https://api.todoist.com/rest/v2` |
| Sync v9 (deprecated, 410) | `https://api.todoist.com/sync/v9` |

---

## Pagination

All list endpoints use cursor-based pagination. Response shape:
```json
{
  "results": [...],    // or "items" for completed endpoints
  "next_cursor": "..." // null on last page
}
```
The helper `_fetch_all_pages(url, results_key, params)` in `fetcher.py` handles this.

---

## Snippets

**Rule: never print anything that contains the token. Build headers inline but do not print them.**

---

### 1. Account / plan info
```python
import requests
from the_main_quest.todoist_snapshot.fetcher import _headers

resp = requests.post("https://api.todoist.com/api/v1/sync", headers=_headers(),
                     json={"sync_token": "*", "resource_types": ["user"]}, timeout=15)
user = resp.json().get("user", {})
print("is_premium:", user.get("is_premium"))
print("plan_name:", user.get("plan_name"))
```
**Goal:** Confirm whether the account is free or Pro — determines which completed-task endpoints work.

---

### 2. Active tasks (sample)
```python
import requests, json
from the_main_quest.todoist_snapshot.fetcher import _headers

resp = requests.get("https://api.todoist.com/api/v1/tasks", headers=_headers(),
                    params={"limit": 3}, timeout=15)
data = resp.json()
print("status:", resp.status_code)
print("next_cursor:", data.get("next_cursor"))
tasks = data.get("results", [])
print(f"returned {len(tasks)} tasks")
if tasks:
    print(json.dumps(tasks[0], indent=2, default=str))
```
**Look for:** field names (`id`, `content`, `due.date`, `due.is_recurring`, `created_at`, `labels`).

---

### 3. Recurring tasks specifically
```python
import requests, json
from the_main_quest.todoist_snapshot.fetcher import _headers

resp = requests.get("https://api.todoist.com/api/v1/tasks", headers=_headers(),
                    params={"limit": 50}, timeout=15)
tasks = resp.json().get("results", [])
recurring = [t for t in tasks if (t.get("due") or {}).get("is_recurring")]
print(f"recurring tasks found: {len(recurring)}")
for t in recurring[:3]:
    print("  id:", t["id"], "due:", t.get("due"), "content:", t.get("content", "")[:50])
```
**Goal:** Confirm `is_recurring` lives inside the `due` object; verify due dates are present.

---

### 4. Completed tasks — by completion date (Pro endpoint)
```python
import requests
from datetime import datetime, timezone
from the_main_quest.todoist_snapshot.fetcher import _headers

now = datetime.now(timezone.utc)
since = now.strftime("%Y-%m-%dT00:00:00Z")
until = now.strftime("%Y-%m-%dT23:59:59Z")

resp = requests.get(
    "https://api.todoist.com/api/v1/tasks/completed/by_completion_date",
    headers=_headers(), params={"since": since, "until": until, "limit": 5}, timeout=15
)
print("status:", resp.status_code)  # 403 = free plan, 200 = Pro
data = resp.json()
items = data.get("items", [])
print(f"completed today: {len(items)}")
if items:
    import json
    print(json.dumps(items[0], indent=2, default=str))
```
**Goal:** Check accessibility; if 200, inspect whether `is_recurring=True` tasks appear here.

---

### 5. Completed tasks — wider date range
```python
import requests, json
from the_main_quest.todoist_snapshot.fetcher import _headers

resp = requests.get(
    "https://api.todoist.com/api/v1/tasks/completed/by_completion_date",
    headers=_headers(),
    params={"since": "2026-02-01T00:00:00Z", "until": "2026-03-01T23:59:59Z", "limit": 5},
    timeout=15,
)
print("status:", resp.status_code)
items = resp.json().get("items", [])
print(f"count: {len(items)}")
if items:
    print(json.dumps(items[0], indent=2, default=str))
```
**Look for:** Whether `due.is_recurring=True` tasks appear; what `completed_at` looks like;
whether `due.date` is the OLD due date or the new rescheduled one.

---

### 6. Sync API — items (check for completed/checked tasks)
```python
import requests, json
from the_main_quest.todoist_snapshot.fetcher import _headers

resp = requests.post(
    "https://api.todoist.com/api/v1/sync",
    headers=_headers(),
    json={"sync_token": "*", "resource_types": ["items"]},
    timeout=15,
)
data = resp.json()
items = data.get("items", [])
completed = [i for i in items if i.get("completed_at") or i.get("checked")]
print(f"total items: {len(items)}, with completion marker: {len(completed)}")
if completed:
    print(json.dumps(completed[0], indent=2, default=str))
```
**Goal:** Check if recently completed items are included in sync `items`, and what fields mark them.

---

### 7. Sync API — probe all resource_types
```python
import requests
from the_main_quest.todoist_snapshot.fetcher import _headers

for resource in ["items", "projects", "sections", "labels", "user", "filters",
                 "reminders", "notes", "live_notifications",
                 "completed_items", "karma_stats"]:
    resp = requests.post(
        "https://api.todoist.com/api/v1/sync",
        headers=_headers(),
        json={"sync_token": "*", "resource_types": [resource]},
        timeout=10,
    )
    result = resp.json()
    has_data = resource in result and bool(result[resource])
    print(f"{resource:25s} → status={resp.status_code}  key_present={resource in result}  has_data={has_data}")
```
**Goal:** Find whether `completed_items` or similar resource type exists and returns data.

---

### 8. After completing a recurring task — verify due date shift
Complete a recurring task in the Todoist app, then immediately run:
```python
import requests, json
from the_main_quest.todoist_snapshot.fetcher import _headers

task_id = "PASTE_TASK_ID_HERE"
resp = requests.get(f"https://api.todoist.com/api/v1/tasks/{task_id}",
                    headers=_headers(), timeout=10)
print("status:", resp.status_code)
if resp.status_code == 200:
    t = resp.json()
    print("due:", t.get("due"))
    print("completed_at:", t.get("completed_at"))
else:
    # 404 means task was completed and rescheduled under a new ID
    print("task not found — may have been reassigned a new ID")

# Also check if it appears in active list with new due date
resp2 = requests.get("https://api.todoist.com/api/v1/tasks", headers=_headers(),
                     params={"limit": 50}, timeout=15)
tasks = resp2.json().get("results", [])
match = [t for t in tasks if t["id"] == task_id]
if match:
    print("found in active list with due:", match[0].get("due"))
else:
    print("not in active list with original ID")
```
**Goal:** Confirm whether the same `task_id` persists after completion with a new due date,
or whether Todoist creates a new task ID for the rescheduled instance.
This is critical for the `prev_due_date` detection approach.

---

## Key questions to answer

1. **Plan:** Is `is_premium` True or False?
2. **Completed endpoint:** Does `completed/by_completion_date` return 200 or 403?
3. **Recurring in completed endpoint:** Do recurring task completions appear there? What does `due.date` contain — the old due date or the new rescheduled one?
4. **Sync completed_items:** Does `resource_types: ["completed_items"]` return anything?
5. **Task ID persistence:** After completing a recurring task, does the same `task_id` reappear with a new due date, or is a new ID created?
6. **Due date after completion:** Confirm the active task list shows the rescheduled due date (e.g. tomorrow) for a just-completed recurring task.

---

## Deciding the final design

| Scenario | Completion detection approach |
|---|---|
| `completed/by_completion_date` accessible + includes recurring completions | Use API for everything; no two-table split needed |
| `completed/by_completion_date` accessible but recurring completions absent | API for non-recurring; due-date shift for recurring |
| `completed/by_completion_date` inaccessible (free plan) | Due-date shift for recurring only; non-recurring completions not tracked |
| Same `task_id` does NOT persist after completion | Due-date shift approach is impossible; need alternative |
| `completed_items` sync resource available | Use sync API instead of REST completed endpoint |
