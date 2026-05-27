from __future__ import annotations

import sys
import os

from .tui import run_main, run_archive, run_settings


def main() -> None:
    if "--dev" in sys.argv:
        _run_dev()
    elif len(sys.argv) > 1 and sys.argv[1] == "archive":
        run_archive()
    elif len(sys.argv) > 1 and sys.argv[1] == "update":
        _run_update()
    elif len(sys.argv) > 1 and sys.argv[1] == "add":
        _run_add()
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        _run_list()
    else:
        run_main()


def _cli_ensure_unlocked() -> None:
    from . import db
    if db.is_encryption_enabled():
        import getpass
        attempts = 0
        while attempts < 3:
            prompt_text = "Database is encrypted. Enter password: " if attempts == 0 else f"Incorrect password. Try again: "
            try:
                password = getpass.getpass(prompt_text)
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                sys.exit(0)
            if db.set_encryption_key_from_password(password):
                return
            attempts += 1
        print("✗ Too many incorrect attempts. Exiting.")
        sys.exit(1)


def _run_add() -> None:
    if len(sys.argv) < 3 or not sys.argv[2].strip():
        print("Usage: td add <task_text>")
        sys.exit(1)
    
    task_text = sys.argv[2].strip()
    _cli_ensure_unlocked()
    
    from . import db
    result = db.add_task(task_text)
    if result is None:
        print("✗ Failed to add task (maximum active tasks reached).")
        sys.exit(1)
    print(f"✓ Task added successfully (ID: {result['id']})")


def _run_list() -> None:
    _cli_ensure_unlocked()
    from . import db
    from rich.console import Console
    from rich.text import Text

    tasks = db.get_active_tasks()
    console = Console()
    
    open_count = sum(1 for t in tasks if t["status"] == "active")
    completed_count = db.get_completed_count()
    header = Text("td • ", style="bold")
    header.append(Text(f"{open_count} open", style="dim"))
    header.append(Text(" / ", style="dim"))
    header.append(Text(f"{completed_count} completed", style="dim"))
    console.print(header)
    
    console.print(Text("─" * 40, style="dim"))
    
    if not tasks:
        console.print(Text("  No tasks found.", style="dim"))
        return
        
    for i, task in enumerate(tasks, 1):
        is_done = task["status"] == "done"
        marker = "✓" if is_done else "○"
        
        text = task["text"]
        if is_done:
            line_text = Text(text, style="strike dim")
            marker_text = Text(marker, style="green bold")
        else:
            line_text = Text(text)
            marker_text = Text(marker, style="yellow")
            
        line = Text("  ")
        line.append(marker_text)
        line.append(" ")
        line.append(line_text)
        console.print(line)


def _run_update() -> None:
    """Update td to the latest version from PyPI."""
    import subprocess
    print("Updating td...")
    result = subprocess.run(
        ["uv", "tool", "upgrade", "lucaspon-td"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        print("✓ td updated successfully")
    else:
        print(f"✗ update failed: {result.stderr.strip()}")
        sys.exit(1)


def _run_dev() -> None:
    """Watch src/td/ for changes and restart the TUI automatically."""
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    import subprocess
    import time

    src_dir = os.path.dirname(__file__)

    class RestartHandler(FileSystemEventHandler):
        def __init__(self):
            self.changed = False

        def on_modified(self, event):
            if event.src_path.endswith(".py"):
                self.changed = True

        def on_created(self, event):
            if event.src_path.endswith(".py"):
                self.changed = True

    observer = Observer()
    handler = RestartHandler()
    observer.schedule(handler, src_dir, recursive=True)
    observer.start()

    print("td --dev: watching for changes... (Ctrl+C to stop)")
    subprocess.run(["uv", "run", "td"])
    try:
        while True:
            time.sleep(0.5)
            if handler.changed:
                handler.changed = False
                print("\n⟳  Change detected, restarting...\n")
                subprocess.run(["uv", "run", "td"])
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()