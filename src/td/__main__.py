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
    else:
        run_main()


def _run_update() -> None:
    """Update td to the latest version from PyPI."""
    import subprocess
    print("Updating td...")
    result = subprocess.run(
        ["uv", "tool", "upgrade", "td"],
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