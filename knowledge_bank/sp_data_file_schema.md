# SP Data File Schema — Pipeline Reference

Observed from live sync-data.json. Use this as the authoritative reference when
implementing `the_main_quest/sp_snapshot/reader.py` and related pipeline modules.

---

## Files

| File | Location on disk | Contains |
|---|---|---|
| `sync-data.json` | `.../webdav/data/users/karan/sync-data.json` | All active tasks + incomplete recurring instances |
| `archive.json` | `.../webdav/data/users/karan/archive.json` | Historically completed tasks (post Finish Day) |

**`archive.json` does not exist until the first Finish Day is run.**

### File format

Both files are prefixed with `pf_2__` before the JSON payload. Strip this before parsing:

```python
PREFIX = "pf_2__"
with open(path) as f:
    raw = f.read()
data = json.loads(raw[len(PREFIX):])
state = data["state"]
```

Top-level keys in `data`: `version`, `syncVersion`, `schemaVersion`, `vectorClock`,
`lastModified`, `clientId`, `state`.

---

## State keys

```
state.task            — active task entities
state.taskRepeatCfg   — recurring task config entities
state.project         — project entities
state.tag             — tag entities
state.menuTree        — folder structure (project folders + tag folders)
state.archiveYoung    — recently archived tasks (short-term, before full archive)
state.archiveOld      — (present in archive.json) fully archived tasks
```

---

## Task entity

```json
{
  "id":             "TkJOjnCKMDBhKbBT4aqhI",
  "title":          "Listen To Affirmations",
  "notes":          "markdown string or absent",
  "projectId":      "QL_jXPrdbprA4xOffntQe",
  "tagIds":         ["s9r5GTdzPsRa6Nk0oU7c2"],
  "parentId":       null,
  "subTaskIds":     [],
  "isDone":         false,
  "doneOn":         null,
  "created":        1773856038403,
  "modified":       1773856038412,
  "dueDay":         "2026-03-18",
  "timeEstimate":   0,
  "timeSpent":      0,
  "timeSpentOnDay": {},
  "repeatCfgId":    "jobEgHO62er1uK2SCPFNY",
  "attachments":    []
}
```

### Key fields for the pipeline

| Field | Type | Notes |
|---|---|---|
| `id` | string | 21-char nanoid — stable identifier |
| `title` | string | Task name |
| `notes` | string \| absent | Markdown description. Key may be absent entirely (not null) |
| `projectId` | string \| null | ID of the containing project. Null for inbox tasks |
| `tagIds` | string[] | IDs of applied tags — resolve via `state.tag.entities` |
| `parentId` | string \| null | Set if this is a subtask. Absent or null for top-level |
| `subTaskIds` | string[] | IDs of child tasks |
| `isDone` | boolean | True when the task has been ticked off |
| `doneOn` | number \| null | Unix ms timestamp of completion. Null until completed |
| `created` | number | Unix ms. For recurring instances: set to `lastTaskCreation` of the config (the scheduled occurrence time), NOT wall clock |
| `modified` | number | Unix ms of last modification |
| `dueDay` | string \| absent | "YYYY-MM-DD" due date |
| `dueWithTime` | number \| absent | Unix ms — when due date has a specific time |
| `timeEstimate` | number | ms. 0 = no estimate |
| `timeSpent` | number | Total ms spent (sum of timeSpentOnDay values) |
| `timeSpentOnDay` | object | `{"YYYY-MM-DD": ms}` — per-day time tracking. Empty until timer is used |
| `repeatCfgId` | string \| null | Links to TaskRepeatCfg. Null for non-recurring tasks |

### Bidirectional references — use task fields as authoritative

`project.entities[id].taskIds` and `tag.entities[id].taskIds` also list task IDs
as reverse indexes. **Use the task's own `projectId` and `tagIds` as the source of
truth** — do not rely on the reverse indexes, they may be stale.

---

## TaskRepeatCfg entity

```json
{
  "id":                    "jobEgHO62er1uK2SCPFNY",
  "title":                 "Listen To Affirmations",
  "projectId":             "QL_jXPrdbprA4xOffntQe",
  "tagIds":                ["s9r5GTdzPsRa6Nk0oU7c2"],
  "repeatCycle":           "DAILY",
  "repeatEvery":           1,
  "quickSetting":          "DAILY",
  "monday":    true,  "tuesday":  true,  "wednesday": true,
  "thursday":  true,  "friday":   true,  "saturday":  false, "sunday": false,
  "repeatFromCompletionDate": false,
  "defaultEstimate":       0,
  "startDate":             "2026-03-18",
  "isPaused":              false,
  "lastTaskCreation":      1773815400000,
  "lastTaskCreationDay":   "2026-03-18",
  "skipOverdue":           false,
  "shouldInheritSubtasks": false,
  "subTaskTemplates":      [],
  "order":                 0
}
```

### Key fields for the pipeline

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable config ID — links to `task.repeatCfgId` |
| `title` | string | Template title — each instance inherits this |
| `projectId` | string \| null | Project for generated instances |
| `tagIds` | string[] | Tags applied to each instance |
| `repeatCycle` | string | `"DAILY"` \| `"WEEKLY"` \| `"MONTHLY"` \| `"YEARLY"` |
| `repeatEvery` | number | Every N cycles |
| `monday`…`sunday` | boolean | Which days of the week instances are created |
| `repeatFromCompletionDate` | boolean | If true, next instance is scheduled from completion, not calendar |
| `defaultEstimate` | number | ms |
| `startDate` | string | "YYYY-MM-DD" — when the config became active |
| `isPaused` | boolean | No new instances created when true |
| `lastTaskCreation` | number | Unix ms of the last generated instance |
| `lastTaskCreationDay` | string | "YYYY-MM-DD" of the last generated instance |
| `quickSetting` | string | `"DAILY"` \| `"WEEKLY"` \| `"CUSTOM"` — UI shortcut used |

### Important: instance creation requires the app to be open

SP generates recurring instances **only when the app is opened on any device**.
If no device opens SP for a day, no instance is created for that day.
`lastTaskCreationDay` reflects only the days the app was opened.

---

## Project entity

```json
{
  "id":              "QL_jXPrdbprA4xOffntQe",
  "title":           "Mental Health",
  "taskIds":         ["RbddAcAmL7xGszqFqhcKu", "TkJOjnCKMDBhKbBT4aqhI"],
  "backlogTaskIds":  [],
  "noteIds":         [],
  "isHiddenFromMenu": false,
  "isArchived":      false,
  "isEnableBacklog": true,
  "icon":            null,
  "theme":           {...},
  "advancedCfg":     {...}
}
```

Project folder membership is in `menuTree.projectTree` — **not** in the project entity itself.
To resolve which folder a project belongs to, walk `menuTree.projectTree`.

---

## Tag entity

```json
{
  "id":      "s9r5GTdzPsRa6Nk0oU7c2",
  "title":   "Mental Health",
  "color":   "#a05db1",
  "created": 1773855906822,
  "taskIds": ["RbddAcAmL7xGszqFqhcKu", "TkJOjnCKMDBhKbBT4aqhI"],
  "icon":    null,
  "theme":   {...},
  "advancedCfg": {...}
}
```

Tag folder membership is in `menuTree.tagTree` — not in the tag entity itself.

---

## menuTree — folder structure

```json
{
  "projectTree": [
    {
      "k": "f",
      "id": "7abcc859-a429-4e59-b394-f09e5b0c336f",
      "name": "Health",
      "isExpanded": true,
      "children": [
        { "k": "p", "id": "QL_jXPrdbprA4xOffntQe" },
        { "k": "p", "id": "ln4l1bbCXsSmiPDKAdTgT" }
      ]
    }
  ],
  "tagTree": [
    {
      "k": "f",
      "id": "108a7f5e-09f3-4227-9638-3d2d0249d070",
      "name": "Health",
      "isExpanded": true,
      "children": [
        { "k": "t", "id": "s9r5GTdzPsRa6Nk0oU7c2" }
      ]
    }
  ]
}
```

### Node types (`k` field)

| `k` | Meaning | Extra fields |
|---|---|---|
| `"f"` | Folder | `name`, `isExpanded`, `children[]` |
| `"p"` | Project reference | `id` only |
| `"t"` | Tag reference | `id` only |

### Building lookup dicts in reader.py

```python
# project_id -> folder_name
project_folder: dict[str, str] = {}
for node in state["menuTree"]["projectTree"]:
    if node["k"] == "f":
        for child in node["children"]:
            project_folder[child["id"]] = node["name"]

# tag_id -> folder_name
tag_folder: dict[str, str] = {}
for node in state["menuTree"]["tagTree"]:
    if node["k"] == "f":
        for child in node["children"]:
            tag_folder[child["id"]] = node["name"]
```

---

## What's visible before vs after completion

| Field | Before completion | After completion |
|---|---|---|
| `isDone` | `false` | `true` |
| `doneOn` | `null` | Unix ms timestamp |
| `timeSpentOnDay` | `{}` | `{"YYYY-MM-DD": ms, ...}` if timer was used |
| `timeSpent` | `0` | Sum of `timeSpentOnDay` values |

---

## Completion and archiving flow

```
Task ticked off
  → isDone = true, doneOn = <unix ms>
  → Task stays in sync-data.json (state.task)

User runs Finish Day
  → Completed tasks move out of state.task
  → They appear in state.archiveYoung briefly
  → Eventually land in archive.json (state.archiveOld)
```

**The pipeline must read both files** to capture all completed tasks:
- `sync-data.json` → tasks with `isDone: true` not yet archived
- `archive.json` → all historically archived tasks

`archive.json` will not exist until the first Finish Day is run. Handle with `try/except FileNotFoundError`.

---

## Derived fields for the pipeline

### `work_date(done_on_ts)` — correct calendar date for a completion

```python
DAY_BOUNDARY_HOUR = 4  # config: sp_snapshot.day_boundary_hour

def work_date(done_on_ms: int) -> date:
    dt = datetime.fromtimestamp(done_on_ms / 1000, tz=timezone.utc).astimezone(local_tz)
    if dt.hour < DAY_BOUNDARY_HOUR:
        return (dt - timedelta(days=1)).date()
    return dt.date()
```

### Priority from tags

SP has no native priority field. Priority is encoded as tags `p1`–`p4`:

```python
PRIORITY_MAP = {"p1": 4, "p2": 3, "p3": 2, "p4": 1}

def priority_from_tags(tag_ids: list, tag_lookup: dict) -> int | None:
    for tid in tag_ids:
        name = tag_lookup.get(tid, {}).get("title", "")
        if name in PRIORITY_MAP:
            return PRIORITY_MAP[name]
    return None
```

### Repeat days list from config

```python
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def repeat_days(cfg: dict) -> list[str]:
    return [d for d in DAYS if cfg.get(d)]
```

---

## Open questions (verify when archive.json first appears)

1. Does `archive.json` use the same `pf_2__` prefix?
2. Are archived tasks in `state.task` or `state.archiveOld` within the archive file?
3. Do archived tasks retain `doneOn` and `timeSpentOnDay`?
4. Does `archiveYoung` in `sync-data.json` hold tasks between Finish Day and full archive?
