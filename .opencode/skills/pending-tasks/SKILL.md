---
name: pending-tasks
description: Load all incomplete non-recurring Todoist tasks into context by running the fetch script
---

Run the following command and wait for it to complete:

```bash
poetry run python -m runs.fetch_pending_tasks
```

The output is a markdown list of all incomplete, non-recurring Todoist tasks grouped by project.
Use it as the working task list for this conversation — discuss priorities, planning, or anything else the user needs.
