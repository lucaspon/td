from __future__ import annotations

import sys
import tty
import termios
from datetime import datetime, timezone
from rich.console import Console
from rich.text import Text

from . import db

console = Console()

# ANSI escape sequences
ESC = "\x1b"
ARROW_UP = "\x1b[A"
ARROW_DOWN = "\x1b[B"
SHIFT_ARROW_UP = "\x1b[1;2A"
SHIFT_ARROW_DOWN = "\x1b[1;2B"
ALT_ARROW_UP = "\x1b[1;3A"
ALT_ARROW_DOWN = "\x1b[1;3B"
ENTER = "\n"  # ICRNL translates \r from terminal to \n in cbreak mode
BACKSPACE = "\x7f"
DELETE = "\x1b[3~"


def _read_key() -> str:
    """Read a single keypress, handling escape sequences."""
    fd = sys.stdin.fileno()
    ch = sys.stdin.read(1)
    if ch == ESC:
        # Read rest of escape sequence
        seq = ch
        try:
            # Set a short timeout for sequence reading
            old = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[3] = new[3] & ~(termios.ICANON | termios.ECHO)
            new[6][termios.VMIN] = 0
            new[6][termios.VTIME] = 1  # 100ms timeout
            termios.tcsetattr(fd, termios.TCSANOW, new)
            while True:
                c = sys.stdin.read(1)
                if c:
                    seq += c
                    if c.isalpha() or c == "~":
                        break
                else:
                    break
            termios.tcsetattr(fd, termios.TCSANOW, old)
        except Exception:
            pass
        return seq
    return ch


def _clear_screen() -> None:
    console.file.write("\033[2J\033[H")
    console.file.flush()


def _hide_cursor() -> None:
    console.file.write("\033[?25l")
    console.file.flush()


def _show_cursor() -> None:
    console.file.write("\033[?25h")
    console.file.flush()


def _render_main(
    tasks: list[dict],
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    confirm_msg: str = "",
) -> None:
    _clear_screen()
    lines = []
    for i, task in enumerate(tasks):
        is_hovered = i == hover
        is_done = task["status"] == "done"

        prefix = "▸ " if is_hovered else "  "
        marker = "✓" if is_done else "○"

        text = task["text"]
        if not text:
            line_text = Text("_", style="underline dim")
        elif is_done:
            line_text = Text(text, style="strike dim")
        elif is_hovered:
            line_text = Text(text, style="cyan bold")
        else:
            line_text = Text(text)

        line = Text(prefix)
        line.append(marker)
        line.append(" ")
        line.append(line_text)
        lines.append(line)

    if not tasks:
        lines.append(Text("  No tasks. Press n to add one.", style="dim"))

    output = Text("\n").join(lines)
    console.print(output)

    if mode == "edit":
        console.print()
        console.print(Text(f"> {edit_text}_", style="yellow bold"))
    elif mode == "confirm":
        console.print()
        console.print(Text(f"  {confirm_msg}", style="yellow bold"))

    console.print()
    if mode == "normal":
        hint_parts = ["a:add", "e:edit", "d:delete", "Space:done", "c:clear", ",:archive", "Shift+↑↓:reorder", "Alt+↑↓:dup"]
    elif mode == "edit":
        hint_parts = ["Esc:cancel", "Enter:confirm"]
    elif mode == "confirm":
        hint_parts = ["y/Enter:confirm", "Esc:cancel"]
    else:
        hint_parts = []
    console.print(Text("  " + " │ ".join(hint_parts), style="dim"))


def _render_archive(tasks: list[dict], scroll: int, term_height: int) -> None:
    _clear_screen()
    console.print(Text("Archive", style="bold cyan"), Text(f"  ({len(tasks)} tasks)", style="dim"))
    console.print()

    if not tasks:
        console.print(Text("  No archived tasks.", style="dim"))
    else:
        visible = tasks[scroll:]
        max_lines = term_height - 4
        line_count = 0
        for task in visible:
            if line_count >= max_lines:
                break
            def fmt(iso: str | None) -> str:
                if not iso:
                    return ""
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                local = dt.astimezone()
                return local.strftime("%Y-%m-%d %H:%M")

            line = Text("  ")
            line.append(Text(task["text"], style="bold"))
            line.append(Text(f"  created {fmt(task['created_at'])}", style="dim"))
            if task["done_at"]:
                line.append(Text(f"  done {fmt(task['done_at'])}", style="dim"))
            line.append(Text(f"  archived {fmt(task['archived_at'])}", style="dim"))
            console.print(line)
            line_count += 1

    console.print(Text("  ↑/k ↓/j scroll │ q:quit", style="dim"))


def run_main() -> None:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    _hide_cursor()
    try:
        tty.setcbreak(fd)
        hover = 0
        mode = "normal"
        edit_task_id: int | None = None
        edit_text = ""
        confirm_action: str = ""  # "delete" or "archive"
        confirm_task_id: int | None = None

        while True:
            tasks = db.get_active_tasks()
            if tasks and hover >= len(tasks):
                hover = len(tasks) - 1
            if not tasks:
                hover = 0

            if mode == "confirm" and confirm_action == "archive":
                confirm_msg = "Clear all done tasks? y/n"
            elif mode == "confirm" and confirm_action == "delete":
                task_text = next((t["text"] for t in tasks if t["id"] == confirm_task_id), "")
                confirm_msg = f'Delete "{task_text}"? y/n'
            else:
                confirm_msg = ""

            _render_main(tasks, hover, mode, edit_text, confirm_msg)

            key = _read_key()

            if mode == "normal":
                if key in ("q", ESC):
                    break
                elif key == SHIFT_ARROW_UP:
                    if tasks and hover > 0:
                        db.move_task(tasks[hover]["id"], -1)
                        hover -= 1
                elif key == SHIFT_ARROW_DOWN:
                    if tasks and hover < len(tasks) - 1:
                        db.move_task(tasks[hover]["id"], 1)
                        hover += 1
                elif key == ALT_ARROW_UP:
                    if tasks and hover > 0:
                        db.duplicate_task(tasks[hover]["id"], -1)
                        tasks = db.get_active_tasks()
                        hover -= 1
                elif key == ALT_ARROW_DOWN:
                    if tasks and len(tasks) < db.MAX_ACTIVE_TASKS:
                        db.duplicate_task(tasks[hover]["id"], 1)
                        tasks = db.get_active_tasks()
                        hover += 1
                elif key in (ARROW_UP, "k"):
                    if hover > 0:
                        hover -= 1
                elif key in (ARROW_DOWN, "j"):
                    if tasks and hover < len(tasks) - 1:
                        hover += 1
                elif key in (ENTER, "e"):
                    if tasks:
                        mode = "edit"
                        edit_task_id = tasks[hover]["id"]
                        edit_text = tasks[hover]["text"]
                elif key == "a":
                    if len(tasks) < db.MAX_ACTIVE_TASKS:
                        new_task = db.add_task("")
                        if new_task:
                            tasks = db.get_active_tasks()
                            hover = len(tasks) - 1
                            edit_task_id = new_task["id"]
                            edit_text = ""
                            mode = "edit"
                elif key == "d":
                    if tasks:
                        confirm_action = "delete"
                        confirm_task_id = tasks[hover]["id"]
                        mode = "confirm"
                elif key == "c":
                    done_count = sum(1 for t in tasks if t["status"] == "done")
                    if done_count > 0:
                        confirm_action = "archive"
                        confirm_task_id = None
                        mode = "confirm"
                elif key == " ":
                    if tasks:
                        db.toggle_done(tasks[hover]["id"])
                elif key == ",":
                    # Switch to archive view
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _show_cursor()
                    run_archive()
                    _hide_cursor()
                    tty.setcbreak(fd)
                    continue

            elif mode == "confirm":
                if key in ("y", ENTER):
                    if confirm_action == "delete" and confirm_task_id is not None:
                        db.delete_task(confirm_task_id)
                        tasks = db.get_active_tasks()
                        if hover >= len(tasks) and hover > 0:
                            hover = len(tasks) - 1
                    elif confirm_action == "archive":
                        db.archive_done()
                    mode = "normal"
                    confirm_action = ""
                    confirm_task_id = None
                else:
                    mode = "normal"
                    confirm_action = ""
                    confirm_task_id = None

            elif mode == "edit":
                if key == ESC:
                    # If task text is empty, delete it
                    if edit_task_id:
                        current = next((t for t in db.get_active_tasks() if t["id"] == edit_task_id), None)
                        if current and not current["text"]:
                            db.delete_task(edit_task_id)
                    mode = "normal"
                    edit_task_id = None
                    edit_text = ""
                elif key == ENTER:
                    if edit_task_id:
                        db.update_task_text(edit_task_id, edit_text)
                    mode = "normal"
                    edit_task_id = None
                    edit_text = ""
                elif key == BACKSPACE:
                    edit_text = edit_text[:-1]
                elif key == DELETE:
                    edit_text = edit_text[:-1]
                elif key in (ARROW_UP, ARROW_DOWN):
                    pass  # Ignore arrow keys in edit mode
                elif len(key) == 1 and ord(key) >= 32:
                    edit_text += key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _show_cursor()
        _clear_screen()


def run_archive() -> None:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    _hide_cursor()
    try:
        tty.setcbreak(fd)
        scroll = 0
        term_height = console.height

        while True:
            tasks = db.get_archived_tasks()
            _render_archive(tasks, scroll, term_height)

            key = _read_key()
            if key in ("q", ESC):
                break
            elif key in (ARROW_UP, "k"):
                if scroll > 0:
                    scroll -= 1
            elif key in (ARROW_DOWN, "j"):
                if scroll < len(tasks) - 1:
                    scroll += 1
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _show_cursor()
        _clear_screen()