"""
Integration tests for the Todoist fetch layer — hits the real API.
Requires config.todoist.api_token to be set via SECRETS_DIRECTORY.
"""

from the_main_quest.todoist_snapshot import fetcher


def test_fetch_active_tasks_returns_list():
    tasks = fetcher.fetch_active_tasks()
    assert isinstance(tasks, list)


def test_active_task_shape():
    tasks = fetcher.fetch_active_tasks()
    if not tasks:
        return
    task = tasks[0]
    assert "id" in task
    assert "content" in task
    assert isinstance(task.get("labels"), list)
    # due is either None or a dict with date/is_recurring
    if task.get("due"):
        assert "date" in task["due"]
        assert "is_recurring" in task["due"]


def test_fetch_completed_today_returns_typed_tuple():
    items, pro = fetcher.fetch_completed_today()
    assert isinstance(items, list)
    assert isinstance(pro, bool)


def test_fetch_projects_returns_str_str_dict():
    projects = fetcher.fetch_projects()
    assert isinstance(projects, dict)
    for k, v in projects.items():
        assert isinstance(k, str) and isinstance(v, str)


def test_fetch_sections_returns_str_str_dict():
    sections = fetcher.fetch_sections()
    assert isinstance(sections, dict)
    for k, v in sections.items():
        assert isinstance(k, str) and isinstance(v, str)
