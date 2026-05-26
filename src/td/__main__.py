from __future__ import annotations

import sys
import os

from .tui import run_main, run_archive


def main() -> None:
    if "--dev" in sys.argv:
        _run_dev()
    elif len(sys.argv) > 1 and sys.argv[1] == "archive":
        run_archive()
    else:
        run_main()


def _run_dev() -> None:
    """Watch src/td/ for changes and restart the TUI automatically."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("watchdog is required for --dev mode. Install it with: uv add --dev watchdog")
        sys.exit(1)

    import subprocess
    import time

    src_dir = os.path.join(os.path.dirname(__file__))

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
    process = subprocess.run([sys.executable, "-m", "td"])
    try:
        while True:
            time.sleep(0.5)
            if handler.changed:
                handler.changed = False
                print("\n⟳  Change detected, restarting...\n")
                process = subprocess.run([sys.executable, "-m", "td"])
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()