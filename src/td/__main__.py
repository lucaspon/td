from __future__ import annotations

import sys
import os

from .tui import run_main, run_archive, run_settings


def _parse_list_arg() -> tuple[str, bool, list[str]]:
    """
    Parse list argument from sys.argv and return (list_name, has_list_arg, cleaned_args).
    This handles --list=xxx, -l=xxx, --list xxx, and -l xxx.
    """
    list_name = "main"
    has_list_arg = False
    cleaned_args = []

    i = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg.startswith("--list="):
            list_name = arg.split("=", 1)[1].strip() or "main"
            has_list_arg = True
        elif arg.startswith("-l="):
            list_name = arg.split("=", 1)[1].strip() or "main"
            has_list_arg = True
        elif arg in ("--list", "-l"):
            has_list_arg = True
            if i + 1 < len(sys.argv):
                list_name = sys.argv[i + 1].strip() or "main"
                i += 1  # Skip the value
            else:
                list_name = "main"
        else:
            cleaned_args.append(arg)
        i += 1
    return list_name, has_list_arg, cleaned_args


def main() -> None:
    try:
        list_name, has_list, args = _parse_list_arg()

        if "-V" in args or "--version" in args:
            from importlib.metadata import version as _pkg_version
            print(f"td {_pkg_version('td-task')}")
            return
        elif "-h" in args or "--help" in args or (len(args) > 1 and args[1] in ("help", "-help", "--help")):
            _run_help()
        elif "--dev" in args:
            _run_dev()
        elif len(args) > 1 and args[1] in ("archive", "-archive", "--archive"):
            if not has_list:
                print("✗ Error: list name is required. Pass list name with -l <name> or --list <name>.")
                sys.exit(1)
            run_archive(list_name, lock_list=has_list)
        elif len(args) > 1 and args[1] in ("update", "-update", "--update"):
            _run_update()
        elif len(args) > 1 and args[1] in ("add", "-add", "--add"):
            if not has_list:
                print("✗ Error: list name is required. Pass list name with -l <name> or --list <name>.")
                sys.exit(1)
            _run_add(list_name, args)
        elif len(args) > 1 and args[1] in ("list", "-list", "--list"):
            if not has_list:
                print("✗ Error: list name is required. Pass list name with -l <name> or --list <name>.")
                sys.exit(1)
            _run_list(list_name)
        elif len(args) > 1 and args[1] in ("export", "-export", "--export"):
            _run_export(args)
        elif len(args) > 1 and args[1] in ("import", "-import", "--import"):
            _run_import(args)
        else:
            from . import db
            lists = db.get_all_lists()
            if not lists:
                db.create_list("main")
                lists = ["main"]
            active_list = list_name if has_list else lists[0]
            run_main(active_list, lock_list=has_list)
    except KeyboardInterrupt:
        sys.exit(0)


def _run_help() -> None:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table

    console = Console()
    
    header = Text("td • ", style="bold cyan")
    header.append(Text("minimal TUI & CLI multi-list todo manager", style="italic dim"))
    console.print(header)
    console.print(Text("─" * 60, style="dim"))
    console.print()
    
    console.print(Text("Description for LLMs & Users:", style="bold yellow"))
    console.print(
        "  `td` is a production-grade terminal todo application featuring multi-list\n"
        "  support, encryption, priority starring (pinning), and smooth list transitions.\n"
        "  It works seamlessly interactively (TUI) and scriptably (CLI commands).",
        markup=False
    )
    console.print()
    
    console.print(Text("Usage:", style="bold yellow"))
    console.print("  td [command] [options] [--list=<list_name>]", markup=False)
    console.print()
    
    console.print(Text("Commands:", style="bold yellow"))
    
    commands_table = Table.grid(padding=(0, 2))
    commands_table.add_column(style="green")
    commands_table.add_column()
    
    commands_table.add_row("  (default)", "Launch interactive TUI todo app (defaults to 'main' list)")
    commands_table.add_row("  add <text>", "Add a new task to active or specified list")
    commands_table.add_row("  list", "Print active tasks sequentially between dividers")
    commands_table.add_row("  archive", "Open TUI directly in the completed archive screen")
    commands_table.add_row("  export [file]", "Export database to JSON file or print to stdout")
    commands_table.add_row("  import <file>", "Import and merge database records from a JSON file")
    commands_table.add_row("  update", "Upgrade the `td` package to the latest version")
    
    console.print(commands_table)
    console.print()
    
    console.print(Text("Flags & Parameters:", style="bold yellow"))
    
    options_table = Table.grid(padding=(0, 2))
    options_table.add_column(style="green")
    options_table.add_column()
    
    options_table.add_row("  -l, --list <name>", "Specify/create list context (TUI list-lock, CLI scope)")
    options_table.add_row("  --dev", "Watch source code directory and restart interactive TUI on changes")
    options_table.add_row("  -h, --help", "Print this detailed, LLM-friendly help menu and exit")
    
    console.print(options_table)
    console.print()
    
    console.print(Text("List Operations & Keybindings:", style="bold yellow"))
    console.print("  • Switch lists: Press Left / Right arrows inside normal TUI mode (unlocked).", markup=False)
    console.print("  • Create lists: Press 'l' inside normal TUI mode, type list name and press Enter.", markup=False)
    console.print("  • Star / Pin task: Highlight a task and press 's' to pin it to top (bold yellow).", markup=False)
    console.print()


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


def _run_add(list_name: str, args: list[str]) -> None:
    if len(args) < 3 or not args[2].strip():
        print("Usage: td add <task_text> [--list=<list_name>]")
        sys.exit(1)
    
    task_text = args[2].strip()
    _cli_ensure_unlocked()
    
    from . import db
    result = db.add_task(task_text, list_name)
    if result is None:
        print("✗ Failed to add task (maximum active tasks reached).")
        sys.exit(1)
    print(f"✓ Task added successfully to list '{list_name}' (ID: {result['id']})")


def _run_list(list_name: str) -> None:
    _cli_ensure_unlocked()
    from . import db
    from rich.console import Console
    from rich.text import Text

    tasks = db.get_active_tasks(list_name)
    console = Console()
    
    # Top divider
    width = min(40, console.width or 40)
    console.print(Text("─" * width, style="dim"))
    
    if not tasks:
        console.print(Text("  No tasks found.", style="dim"))
    else:
        prev_starred = False
        for i, task in enumerate(tasks, 1):
            is_done = task["status"] == "done"
            is_starred = task.get("starred", 0) == 1
            
            if i > 1 and prev_starred and not is_starred:
                console.print()
                
            if is_starred:
                marker = "★"
            else:
                marker = "✓" if is_done else "○"
            
            text = task["text"]
            if is_done:
                line_text = Text(text, style="strike dim")
                marker_text = Text(marker, style="green bold")
            elif is_starred:
                line_text = Text(text, style="bold yellow")
                marker_text = Text(marker, style="bold yellow")
            else:
                line_text = Text(text)
                marker_text = Text(marker, style="yellow")
                
            line = Text("  ")
            line.append(marker_text)
            line.append(" ")
            line.append(line_text)
            console.print(line)
            prev_starred = is_starred
            
    # Bottom divider
    console.print(Text("─" * width, style="dim"))


def _run_update() -> None:
    """Update td to the latest version from PyPI."""
    import subprocess
    print("Updating td...")
    result = subprocess.run(
        ["uv", "tool", "upgrade", "td-task"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        output = (result.stdout + result.stderr).strip()
        if "Nothing to upgrade" in output:
            print("already up-to-date.")
        else:
            print("✓ td updated successfully")
            _print_changelog()
    else:
        print(f"✗ update failed: {result.stderr.strip()}")
        sys.exit(1)


def _print_changelog() -> None:
    import os
    from rich.console import Console
    from rich.markdown import Markdown

    changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
    if os.path.exists(changelog_path):
        try:
            with open(changelog_path, "r", encoding="utf-8") as f:
                content = f.read()
            console = Console()
            console.print()
            console.print(Markdown(content))
        except Exception:
            pass


def _run_dev() -> None:
    """Watch src/td/ for changes and restart the TUI automatically."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("✗ watchdog is required for --dev mode.")
        print("  Install it with: pip install 'td-task[dev-mode]'")
        sys.exit(1)

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


def _run_export(args: list[str]) -> None:
    _cli_ensure_unlocked()
    from . import db
    try:
        json_data = db.export_to_json()
        if len(args) > 2:
            filepath = args[2].strip()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_data)
            print(f"✓ Database successfully exported to {filepath}")
        else:
            print(json_data)
    except Exception as e:
        print(f"✗ Export failed: {e}")
        sys.exit(1)


def _run_import(args: list[str]) -> None:
    if len(args) < 3:
        print("Usage: td import <filename>")
        sys.exit(1)
    
    filepath = args[2].strip()
    if not os.path.exists(filepath):
        print(f"✗ File not found: {filepath}")
        sys.exit(1)
        
    _cli_ensure_unlocked()
    from . import db
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            json_str = f.read()
        db.import_from_json(json_str)
        print(f"✓ Database successfully imported and merged from {filepath}")
    except Exception as e:
        print(f"✗ Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()