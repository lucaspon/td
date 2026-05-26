from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text

from . import db
from . import terminal as term

console = Console()


def _render_main(
    tasks: list[dict],
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    confirm_msg: str = "",
) -> None:
    term.clear_screen()

    open_count = sum(1 for t in tasks if t["status"] == "active")
    done_count = sum(1 for t in tasks if t["status"] == "done")
    header = Text("td • ", style="bold")
    header.append(Text(f"{open_count} open", style="dim"))
    header.append(Text(" / ", style="dim"))
    header.append(Text(f"{done_count} completed", style="dim"))
    console.print(header)
    console.print(Text("─" * len(f"td • {open_count} open / {done_count} completed"), style="dim"))
    console.print()

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
        lines.append(Text("  No tasks. Press a to add one.", style="dim"))

    output = Text("\n").join(lines)
    console.print(output)

    if mode == "edit":
        console.print()
        console.print(Text(f"> {edit_text}_", style="yellow bold"))
    elif mode == "confirm":
        console.print()
        console.print(Text(f"  {confirm_msg}", style="yellow bold"))

    if mode == "normal":
        hint_parts = ["a:add", "e:edit", "d:delete", "Space:done", "c:clear", ",:view archived", "Shift+↑↓:reorder", "Alt+↑↓:dup"]
    elif mode == "edit":
        hint_parts = ["Esc:cancel", "Enter:confirm"]
    elif mode == "confirm":
        hint_parts = ["Enter:confirm", "Esc:cancel"]
    else:
        hint_parts = []
    hint_text = "  " + " │ ".join(hint_parts)
    console.print()
    console.print(Text("─" * len(hint_text), style="dim"))
    console.print()
    console.print(Text(hint_text, style="dim"))


def _render_archive(tasks: list[dict], scroll: int, term_height: int) -> None:
    term.clear_screen()
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

    hint_text = "  ↑/k ↓/j scroll │ q:quit"
    console.print()
    console.print(Text("─" * len(hint_text), style="dim"))
    console.print()
    console.print(Text(hint_text, style="dim"))


def _run_main_loop() -> None:
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
            confirm_msg = "Clear all done tasks?"
        elif mode == "confirm" and confirm_action == "delete":
            task_text = next((t["text"] for t in tasks if t["id"] == confirm_task_id), "")
            confirm_msg = f'Delete "{task_text}"?'
        else:
            confirm_msg = ""

        _render_main(tasks, hover, mode, edit_text, confirm_msg)

        key = term.read_key()

        if mode == "normal":
            if key in ("q", term.KEY_ESC):
                break
            elif key == term.KEY_SHIFT_ARROW_UP:
                if tasks and hover > 0:
                    db.move_task(tasks[hover]["id"], -1)
                    hover -= 1
            elif key == term.KEY_SHIFT_ARROW_DOWN:
                if tasks and hover < len(tasks) - 1:
                    db.move_task(tasks[hover]["id"], 1)
                    hover += 1
            elif key == term.KEY_ALT_ARROW_UP:
                if tasks and hover > 0:
                    db.duplicate_task(tasks[hover]["id"], -1)
                    tasks = db.get_active_tasks()
                    hover -= 1
            elif key == term.KEY_ALT_ARROW_DOWN:
                if tasks and len(tasks) < db.MAX_ACTIVE_TASKS:
                    db.duplicate_task(tasks[hover]["id"], 1)
                    tasks = db.get_active_tasks()
                    hover += 1
            elif key in (term.KEY_ARROW_UP, "k"):
                if hover > 0:
                    hover -= 1
            elif key in (term.KEY_ARROW_DOWN, "j"):
                if tasks and hover < len(tasks) - 1:
                    hover += 1
            elif key in (term.KEY_ENTER, "e"):
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
                run_archive()
                continue

        elif mode == "confirm":
            if key in ("y", term.KEY_ENTER):
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
            if key == term.KEY_ESC:
                # If task text is empty, delete it
                if edit_task_id:
                    current = next((t for t in db.get_active_tasks() if t["id"] == edit_task_id), None)
                    if current and not current["text"]:
                        db.delete_task(edit_task_id)
                mode = "normal"
                edit_task_id = None
                edit_text = ""
            elif key == term.KEY_ENTER:
                if edit_task_id:
                    db.update_task_text(edit_task_id, edit_text)
                mode = "normal"
                edit_task_id = None
                edit_text = ""
            elif key == term.KEY_BACKSPACE:
                edit_text = edit_text[:-1]
            elif key == term.KEY_DELETE:
                edit_text = edit_text[:-1]
            elif key in (term.KEY_ARROW_UP, term.KEY_ARROW_DOWN):
                pass
            elif len(key) == 1 and ord(key) >= 32:
                edit_text += key


def _run_archive_loop() -> None:
    scroll = 0
    term_height = console.height

    while True:
        tasks = db.get_archived_tasks()
        _render_archive(tasks, scroll, term_height)

        key = term.read_key()
        if key in ("q", term.KEY_ESC):
            break
        elif key in (term.KEY_ARROW_UP, "k"):
            if scroll > 0:
                scroll -= 1
        elif key in (term.KEY_ARROW_DOWN, "j"):
            if scroll < len(tasks) - 1:
                scroll += 1


def run_main() -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            _run_main_loop()
        finally:
            term.show_cursor()
            term.clear_screen()


def run_archive() -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            _run_archive_loop()
        finally:
            term.show_cursor()
            term.clear_screen()