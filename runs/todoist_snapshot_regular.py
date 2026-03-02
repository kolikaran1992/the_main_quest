"""Entry point: non-recurring task snapshot pipeline."""

from the_main_quest.todoist_snapshot.regular import run

if __name__ == "__main__":
    run()
