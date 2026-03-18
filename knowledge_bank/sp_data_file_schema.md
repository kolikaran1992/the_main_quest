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

### Tag paths — full ancestor chain per tag

Tag folder names are treated as implicit category labels in dashboards.
A task tagged "Mental Health" (which lives under the "Health" folder) implicitly
belongs to both "Health" and "Mental Health" — the pipeline exposes the full path.

The tree supports arbitrary nesting depth (folders inside folders). Whether SP's UI
enforces a max depth is unconfirmed — the walker below handles any depth correctly.

**Floating tags** (tags not placed in any folder) are supported — their path is just
`[tag_name]` with no ancestors.

```python
def build_tag_paths(
    tag_tree: list,
    tag_entities: dict,
) -> dict[str, list[str]]:
    """
    Returns tag_id -> [ancestor_folder_names..., tag_name].

    Examples:
      "Mental Health" under "Health" folder  -> ["Health", "Mental Health"]
      "Urgent" with no folder                -> ["Urgent"]
    """
    result: dict[str, list[str]] = {}

    def walk(nodes: list, ancestors: list[str]) -> None:
        for node in nodes:
            if node["k"] == "f":
                walk(node.get("children", []), ancestors + [node["name"]])
            elif node["k"] == "t":
                tag_name = tag_entities[node["id"]]["title"]
                result[node["id"]] = ancestors + [tag_name]

    walk(tag_tree, [])

    # Floating tags — present in tag_entities but not referenced in the tree
    for tag_id, tag in tag_entities.items():
        if tag_id not in result:
            result[tag_id] = [tag["title"]]

    return result
```

Usage in reader.py:
```python
tag_paths = build_tag_paths(
    state["menuTree"]["tagTree"],
    state["tag"]["entities"],
)
# For a task: tag_paths[task["tagIds"][0]] -> ["Health", "Mental Health"]
```

### Project folder lookup (single level confirmed)

```python
# project_id -> folder_name (or None if not in any folder)
project_folder: dict[str, str | None] = {}
for node in state["menuTree"]["projectTree"]:
    if node["k"] == "f":
        for child in node["children"]:
            project_folder[child["id"]] = node["name"]
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

## Counter tasks — habits with variable count

A convention-based approach to habit tracking that keeps tag grouping intact.
SP's native habit system (`simpleCounter`) has no tag support; this pattern uses
recurring tasks + manual subtasks instead.

### Convention

- Any recurring task tagged `counter_tasks` is treated as a counter habit by the pipeline
- The user manually adds subtasks to each daily instance — one subtask per repetition
- Subtasks are **never** added via `subTaskTemplates` — this is intentional, not a gap
- The parent task is marked done at end of day; subtasks are marked done at the time of each repetition

### What the data shows

```
Parent task (counter habit):
  isDone: true
  doneOn: 1773858517512        ← Unix ms — used by pipeline for work_date()
  tagIds: ["n6TT_1aaUFJs52972nAp4"]  ← includes "counter_tasks" tag
  subTaskIds: ["9PfOGzlrF_I0DjAI4m7jL"]

Subtask (one repetition):
  isDone: false / true          ← true = this repetition was done
  tagIds: []                    ← subtasks carry NO tags
  parentId: "e3EQsKRqlYnRBKQAg5FgK"  ← always points to parent
  projectId: "ln4l1bbCXsSmiPDKAdTgT" ← same project as parent
  doneOn: (unconfirmed — verify by completing a subtask)
```

**Confirmed:** marking the parent done does NOT auto-complete subtasks — they stay
independent. This is required for the count to be meaningful.

### Pipeline logic for counter tasks

```python
COUNTER_TAG = "counter_tasks"

def is_counter_task(task: dict, tag_entities: dict) -> bool:
    return any(
        tag_entities.get(tid, {}).get("title") == COUNTER_TAG
        for tid in task.get("tagIds", [])
    )

def counter_task_count(task: dict, all_tasks: dict) -> int:
    """Number of completed repetitions for this counter task instance."""
    return sum(
        1 for sid in task.get("subTaskIds", [])
        if all_tasks.get(sid, {}).get("isDone") is True
    )
```

Date for a counter task instance = `work_date(task["doneOn"])` on the parent, same
as all other completed tasks.

Tag path resolved via parent `tagIds` — subtask tags are always empty.

### Subtask `doneOn` — unconfirmed

No subtask has been completed individually yet. Whether completed subtasks carry
their own `doneOn` is unknown. For basic count this is irrelevant — `isDone: true`
is sufficient. If per-repetition timestamps are ever needed, verify by completing
a subtask without completing the parent.

---

## Open questions (verify when archive.json first appears)

1. Does `archive.json` use the same `pf_2__` prefix?
2. Are archived tasks in `state.task` or `state.archiveOld` within the archive file?
3. Do archived tasks retain `doneOn` and `timeSpentOnDay`?
4. Does `archiveYoung` in `sync-data.json` hold tasks between Finish Day and full archive?
