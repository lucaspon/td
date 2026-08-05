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
        elif len(args) > 1 and args[1] in ("note", "notes"):
            _run_notes(list_name, has_list, args)
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
            if not lists and not db.get_archived_lists():
                db.create_list("main")
                lists = ["main"]
            active_list = list_name if has_list else (lists[0] if lists else "main")
            run_main(active_list, lock_list=has_list)
    except KeyboardInterrupt:
        sys.exit(0)


def _run_help() -> None:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table

    console = Console()
    
    header = Text("td • ", style="bold cyan")
    header.append(Text("TUI & CLI manager for tasks and Markdown notes", style="italic dim"))
    console.print(header)
    console.print(Text("─" * 60, style="dim"))
    console.print()
    
    console.print(Text("Description for LLMs & Users:", style="bold yellow"))
    console.print(
        "  `td` is a terminal task and Markdown notes manager featuring multi-list\n"
        "  workflows, archiving, encryption, priority starring, and a live note editor.\n"
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
    commands_table.add_row("  notes <action>", "Add, list, show, update, or delete Markdown notes")
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
    console.print("  • Archive lists: Open Lists Menu, press 'A', then use ',' to restore later.", markup=False)
    console.print("  • Create notes: Press 'A', confirm the timestamped name, then edit Markdown.", markup=False)
    console.print("  • Edit notes: Press 'e' or Enter for content, or 'E' for the note name.", markup=False)
    console.print("  • Star / Pin task: Highlight a task and press 's' to pin it to top (bold yellow).", markup=False)
    console.print()


def _cli_ensure_unlocked(list_name: str | None = None) -> None:
    from . import db
    import getpass

    if db.is_encryption_enabled():
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

    if list_name and db.is_list_encryption_enabled(list_name):
        attempts = 0
        while attempts < 3:
            prompt_text = (
                f'List "{list_name}" is encrypted. Enter password: '
                if attempts == 0
                else "Incorrect password. Try again: "
            )
            try:
                password = getpass.getpass(prompt_text)
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                sys.exit(0)
            if db.set_list_encryption_key_from_password(list_name, password):
                return
            attempts += 1
        print("✗ Too many incorrect attempts. Exiting.")
        sys.exit(1)


def _option_value(args: list[str], option: str) -> str | None:
    prefix = f"{option}="
    for index, arg in enumerate(args):
        if arg.startswith(prefix):
            return arg.split("=", 1)[1]
        if arg == option and index + 1 < len(args):
            return args[index + 1]
    return None


def _note_body_from_args(args: list[str]) -> str | None:
    body = _option_value(args, "--body")
    body_file = _option_value(args, "--body-file")
    if body is not None and body_file is not None:
        raise ValueError("Use either --body or --body-file, not both")
    if body_file is not None:
        if body_file == "-":
            return sys.stdin.read()
        from pathlib import Path
        return Path(body_file).read_text(encoding="utf-8")
    return body


def _run_notes(list_name: str, has_list: bool, args: list[str]) -> None:
    import json
    from datetime import datetime
    from . import db

    if len(args) < 3 or args[2] in ("help", "-h", "--help"):
        print("Usage:")
        print("  td notes add [title] --list <name> [--body <markdown> | --body-file <path|->] [--json]")
        print("  td notes list --list <name> [--include-archived] [--json]")
        print("  td notes show <note-id> [--json]")
        print("  td notes update <note-id> [--title <title>] [--body <markdown> | --body-file <path|->] [--json]")
        print("  td notes delete <note-id> [--json]")
        return

    action = args[2]
    json_output = "--json" in args

    if action == "add":
        if not has_list:
            print("✗ Error: list name is required. Pass --list <name>.")
            sys.exit(1)
        _cli_ensure_unlocked(list_name)
        title_option = _option_value(args, "--title")
        title = title_option if title_option is not None else (
            args[3] if len(args) > 3 and not args[3].startswith("--") else ""
        )
        title = title.strip() or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        try:
            body = _note_body_from_args(args)
        except (OSError, ValueError) as error:
            print(f"✗ Failed to read note body: {error}")
            sys.exit(1)
        note = db.add_note(title, list_name)
        if note is None:
            print("✗ Failed to add note (maximum active items reached).")
            sys.exit(1)
        if body is not None:
            db.update_note_content(note["id"], body)
            note["content"] = body
        if json_output:
            print(json.dumps(note, indent=2))
        else:
            print(f"✓ Note added to '{list_name}' (note ID: {note['id']}, task ID: {note['task_id']})")
        return

    if action == "list":
        if not has_list:
            print("✗ Error: list name is required. Pass --list <name>.")
            sys.exit(1)
        _cli_ensure_unlocked(list_name)
        notes = db.get_notes_for_list(list_name, "--include-archived" in args)
        if json_output:
            print(json.dumps(notes, indent=2))
        else:
            for note in notes:
                print(f"{note['id']}\t{note['status']}\t{note['title']}")
        return

    if action not in ("show", "update", "delete") or len(args) < 4:
        print(f"✗ Unknown notes action: {action}")
        sys.exit(1)
    try:
        note_id = int(args[3])
    except ValueError:
        print("✗ Note ID must be an integer.")
        sys.exit(1)
    note_list = db.get_note_list_name(note_id)
    if note_list is None:
        print(f"✗ Note {note_id} not found.")
        sys.exit(1)
    _cli_ensure_unlocked(note_list)

    if action == "show":
        note = db.get_note(note_id)
        if json_output:
            print(json.dumps(note, indent=2))
        else:
            print(note["content"], end="" if note["content"].endswith("\n") else "\n")
        return

    if action == "update":
        title = _option_value(args, "--title")
        try:
            body = _note_body_from_args(args)
        except (OSError, ValueError) as error:
            print(f"✗ Failed to read note body: {error}")
            sys.exit(1)
        if title is None and body is None:
            print("✗ Pass --title, --body, or --body-file.")
            sys.exit(1)
        if title is not None:
            if not title.strip():
                print("✗ Note title cannot be empty.")
                sys.exit(1)
            db.update_note_title(note_id, title)
        if body is not None:
            db.update_note_content(note_id, body)
        updated = db.get_note(note_id)
        if json_output:
            print(json.dumps(updated, indent=2))
        else:
            print(f"✓ Note {note_id} updated.")
        return

    deleted = db.delete_note(note_id)
    if json_output:
        print(json.dumps({"id": note_id, "deleted": deleted}))
    else:
        print(f"✓ Note {note_id} deleted.")


def _run_add(list_name: str, args: list[str]) -> None:
    if len(args) < 3 or not args[2].strip():
        print("Usage: td add <task_text> [--list=<list_name>]")
        sys.exit(1)
    
    task_text = args[2].strip()
    _cli_ensure_unlocked(list_name)
    
    from . import db
    result = db.add_task(task_text, list_name)
    if result is None:
        print("✗ Failed to add task (maximum active tasks reached).")
        sys.exit(1)
    print(f"✓ Task added successfully to list '{list_name}' (ID: {result['id']})")


def _run_list(list_name: str) -> None:
    _cli_ensure_unlocked(list_name)
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
                style = "strike dim underline" if task.get("is_note") else "strike dim"
                line_text = Text(text, style=style)
                marker_text = Text(marker, style="green bold")
            elif is_starred:
                style = "bold yellow underline" if task.get("is_note") else "bold yellow"
                line_text = Text(text, style=style)
                marker_text = Text(marker, style="bold yellow")
            else:
                line_text = Text(text, style="underline" if task.get("is_note") else None)
                marker_text = Text(marker, style="yellow")
                
            line = Text("  ")
            line.append(marker_text)
            line.append(" ")
            line.append(line_text)
            console.print(line)
            prev_starred = is_starred
            
    # Bottom divider
    console.print(Text("─" * width, style="dim"))


def _source_checkout() -> str | None:
    """Return the git checkout td was installed from, or None for a PyPI install."""
    import subprocess
    import tomllib

    try:
        result = subprocess.run(
            ["uv", "tool", "dir"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        receipt = os.path.join(result.stdout.strip(), "td-task", "uv-receipt.toml")
        with open(receipt, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None

    for requirement in data.get("tool", {}).get("requirements", []):
        directory = requirement.get("directory")
        if directory and os.path.isdir(os.path.join(directory, ".git")):
            return directory
    return None


def _source_version(source_dir: str) -> str | None:
    """Read the version declared by the source checkout's pyproject.toml."""
    import tomllib

    try:
        with open(os.path.join(source_dir, "pyproject.toml"), "rb") as f:
            return tomllib.load(f).get("project", {}).get("version")
    except (OSError, ValueError):
        return None


def _run_update() -> None:
    """Update td to the latest version, from the local checkout when installed from one."""
    import subprocess
    from importlib.metadata import version as _pkg_version

    upgrade_cmd = ["uv", "tool", "upgrade", "td-task"]
    source_dir = _source_checkout()

    if source_dir:
        print(f"Pulling latest source from {source_dir}...")
        pull = subprocess.run(
            ["git", "-C", source_dir, "pull", "--ff-only"],
            capture_output=True, text=True, timeout=60,
        )
        if pull.returncode != 0:
            print(f"✗ git pull failed: {pull.stderr.strip()}")
            sys.exit(1)
        try:
            installed = _pkg_version("td-task")
        except Exception:
            installed = None
        if installed and _source_version(source_dir) == installed:
            print("already up-to-date.")
            return
        # A path install keeps resolving to the same requirement, so uv reports
        # nothing to upgrade unless the rebuild is forced.
        upgrade_cmd.append("--reinstall")

    print("Updating td...")
    result = subprocess.run(
        upgrade_cmd, capture_output=True, text=True, timeout=300,
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
