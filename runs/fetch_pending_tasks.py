"""
Fetch all incomplete non-recurring Todoist tasks.

Outputs markdown to stdout — designed to be run by the OpenCode agent
via the pending-tasks skill to load task context into a session.

Run as:
    poetry run python -m runs.fetch_pending_tasks
"""

from datetime import date

from the_main_quest.todoist_snapshot.fetcher import fetch_active_tasks, fetch_projects

_PRIORITY = {1: "p4", 2: "p3", 3: "p2", 4: "p1"}


def main():
    tasks = fetch_active_tasks()
    projects = fetch_projects()  # {project_id: project_name}

    non_recurring = [
        t for t in tasks
        if not (t.get("due") or {}).get("is_recurring")
    ]

    by_project: dict[str, list] = {}
    for t in non_recurring:
        proj_name = projects.get(t.get("project_id", ""), "Inbox")
        by_project.setdefault(proj_name, []).append(t)

    print(f"# Pending Tasks ({len(non_recurring)} total)\n")
    print(f"_As of {date.today()}_\n")

    for proj_name in sorted(by_project):
        items = by_project[proj_name]
        print(f"## {proj_name} ({len(items)})\n")
        for t in items:
            due = (t.get("due") or {}).get("date", "")
            priority = _PRIORITY.get(t.get("priority", 1), "p4")
            labels = t.get("labels", [])

            line = f"- [{priority}]"
            if due:
                line += f" `{due}`"
            line += f" {t['content']}"
            if labels:
                line += "  " + " ".join(f"`{l}`" for l in labels)
            print(line)
        print()


if __name__ == "__main__":
    main()
