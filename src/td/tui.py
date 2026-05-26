from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text

from . import db
from . import terminal as term

console = Console()


def _normal_hint_text() -> str:
    return "  " + " │ ".join(["a:add", "e:edit", "d:delete", "Space:done", "c:clear", ",:view archived", "/:settings", "Shift+↑↓:reorder", "Alt+↑↓:dup"])


def _render_main(
    tasks: list[dict],
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    edit_cursor: int = 0,
    confirm_msg: str = "",
) -> None:
    term.clear_screen()

    open_count = sum(1 for t in tasks if t["status"] == "active")
    completed_count = db.get_completed_count()
    header = Text("td • ", style="bold")
    header.append(Text(f"{open_count} open", style="dim"))
    header.append(Text(" / ", style="dim"))
    header.append(Text(f"{completed_count} completed", style="dim"))
    console.print(header)
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print()

    lines = []
    for i, task in enumerate(tasks):
        is_hovered = i == hover
        is_done = task["status"] == "done"

        prefix = "▸ " if is_hovered else "  "
        marker = "✓" if is_done else "○"

        text = task["text"]
        if not text:
            line_text = Text(" ", style="underline dim")
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
        before = edit_text[:edit_cursor]
        after = edit_text[edit_cursor:]
        console.print()
        console.print(Text(f"> {before}", style="yellow bold"), Text("█", style="yellow"), Text(f"{after}", style="yellow bold"))
    elif mode == "confirm":
        console.print()
        console.print(Text(f"  {confirm_msg}", style="yellow bold"))

    if mode == "edit":
        hint_parts = ["Esc:cancel", "Enter:confirm"]
    elif mode == "confirm":
        hint_parts = ["Enter:confirm", "Esc:cancel"]
    else:
        hint_parts = []
    hint_text = "  " + " │ ".join(hint_parts) if mode != "normal" else _normal_hint_text()
    console.print()
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print(Text(hint_text, style="dim"))


DIVIDER_WIDTH = len(_normal_hint_text())


def _fmt_timestamp(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _render_archive(
    tasks: list[dict],
    hover: int,
    scroll: int,
    term_height: int,
    mode: str = "normal",
    confirm_msg: str = "",
) -> None:
    term.clear_screen()

    header = Text("archive • ", style="bold")
    header.append(Text(f"{len(tasks)} tasks", style="dim"))
    console.print(header)
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print()

    if not tasks:
        console.print(Text("  No archived tasks.", style="dim"))
    else:
        max_lines = term_height - 6  # header(2) + blank + bottom blank + divider + hints
        start = scroll
        end = min(start + max_lines, len(tasks))

        for i in range(start, end):
            task = tasks[i]
            is_hovered = i == hover
            prefix = "▸ " if is_hovered else "  "

            # Build timestamp suffix
            ts_parts = []
            ts_parts.append(f"created {_fmt_timestamp(task['created_at'])}")
            if task["done_at"]:
                ts_parts.append(f"done {_fmt_timestamp(task['done_at'])}")
            ts_parts.append(f"archived {_fmt_timestamp(task['archived_at'])}")
            ts_text = "  ".join(ts_parts)

            line = Text(prefix)
            if is_hovered:
                line.append(Text(task["text"], style="strike bold cyan"))
                line.append(Text(f"  {ts_text}", style="strike dim"))
            else:
                line.append(Text(task["text"], style="strike dim"))
                line.append(Text(f"  {ts_text}", style="strike dim"))
            console.print(line)

    if mode == "confirm":
        console.print()
        console.print(Text(f"  {confirm_msg}", style="yellow bold"))

    # Hints
    archive_hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "d:delete", "r:restore", "c:clear", "q:return"])
    if mode == "confirm":
        hint_text = "  " + " │ ".join(["Enter:confirm", "Esc:cancel"])
    else:
        hint_text = archive_hint_text
    console.print()
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print(Text(hint_text, style="dim"))


def _run_main_loop() -> None:
    hover = 0
    mode = "normal"
    edit_task_id: int | None = None
    edit_text = ""
    edit_cursor = 0
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

        _render_main(tasks, hover, mode, edit_text, edit_cursor, confirm_msg)

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
                if tasks and len(tasks) < db.get_max_tasks():
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
                    edit_cursor = len(edit_text)
            elif key == "a":
                if len(tasks) < db.get_max_tasks():
                    new_task = db.add_task("")
                    if new_task:
                        tasks = db.get_active_tasks()
                        hover = len(tasks) - 1
                        edit_task_id = new_task["id"]
                        edit_text = ""
                        edit_cursor = 0
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
            elif key == "/":
                run_settings()
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
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                if edit_task_id:
                    db.update_task_text(edit_task_id, edit_text)
                mode = "normal"
                edit_task_id = None
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_BACKSPACE:
                if edit_cursor > 0:
                    edit_text = edit_text[:edit_cursor - 1] + edit_text[edit_cursor:]
                    edit_cursor -= 1
            elif key == term.KEY_DELETE:
                if edit_cursor < len(edit_text):
                    edit_text = edit_text[:edit_cursor] + edit_text[edit_cursor + 1:]
            elif key == term.KEY_ARROW_LEFT:
                if edit_cursor > 0:
                    edit_cursor -= 1
            elif key == term.KEY_ARROW_RIGHT:
                if edit_cursor < len(edit_text):
                    edit_cursor += 1
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif key in (term.KEY_ARROW_UP, term.KEY_ARROW_DOWN):
                pass
            elif len(key) == 1 and ord(key) >= 32:
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1


def _run_archive_loop() -> None:
    hover = 0
    scroll = 0
    term_height = console.height or 24
    mode = "normal"
    confirm_action: str = ""  # "delete", "archive", "clear"
    confirm_task_id: int | None = None

    while True:
        tasks = db.get_archived_tasks()
        if not tasks:
            hover = 0
            scroll = 0
        else:
            if hover >= len(tasks):
                hover = len(tasks) - 1
            # Auto-scroll to keep hover visible
            max_lines = term_height - 6
            if hover < scroll:
                scroll = hover
            elif hover >= scroll + max_lines:
                scroll = hover - max_lines + 1

        if mode == "confirm" and confirm_action == "delete":
            task_text = next((t["text"] for t in tasks if t["id"] == confirm_task_id), "")
            confirm_msg = f'Delete "{task_text}"?'
        elif mode == "confirm" and confirm_action == "clear":
            confirm_msg = "Clear all archived tasks?"
        else:
            confirm_msg = ""

        _render_archive(tasks, hover, scroll, term_height, mode, confirm_msg)

        key = term.read_key()

        if mode == "normal":
            if key in ("q", term.KEY_ESC):
                break
            elif key in (term.KEY_ARROW_UP, "k"):
                if hover > 0:
                    hover -= 1
            elif key in (term.KEY_ARROW_DOWN, "j"):
                if tasks and hover < len(tasks) - 1:
                    hover += 1
            elif key == "d":
                if tasks:
                    confirm_action = "delete"
                    confirm_task_id = tasks[hover]["id"]
                    mode = "confirm"
            elif key == "r":
                if tasks:
                    restored = db.restore_task(tasks[hover]["id"])
                    if restored:
                        tasks = db.get_archived_tasks()
                        if hover >= len(tasks) and hover > 0:
                            hover = len(tasks) - 1
            elif key == "c":
                if tasks:
                    confirm_action = "clear"
                    confirm_task_id = None
                    mode = "confirm"

        elif mode == "confirm":
            if key in ("y", term.KEY_ENTER):
                if confirm_action == "delete" and confirm_task_id is not None:
                    db.delete_task(confirm_task_id)
                    tasks = db.get_archived_tasks()
                    if hover >= len(tasks) and hover > 0:
                        hover = len(tasks) - 1
                elif confirm_action == "clear":
                    db.clear_archived()
                    hover = 0
                    scroll = 0
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None
            else:
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None


def _render_settings(
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    edit_cursor: int = 0,
    status_msg: str = "",
) -> None:
    term.clear_screen()

    max_tasks = db.get_max_tasks()

    header = Text("settings • ", style="bold")
    header.append(Text("preferences", style="dim"))
    console.print(header)
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print()

    # Max tasks row
    is_hovered_max = hover == 0
    prefix = "▸ " if is_hovered_max else "  "
    max_line = Text(prefix)
    if mode == "edit" and hover == 0:
        before = edit_text[:edit_cursor]
        after = edit_text[edit_cursor:]
        max_line.append(Text("max tasks: ", style="cyan bold"))
        max_line.append(Text(before, style="yellow bold"))
        max_line.append(Text("█", style="yellow"))
        max_line.append(Text(after, style="yellow bold"))
    elif is_hovered_max:
        max_line.append(Text("max tasks: ", style="cyan bold"))
        max_line.append(Text(str(max_tasks), style="bold"))
    else:
        max_line.append(Text("max tasks: ", style="dim"))
        max_line.append(Text(str(max_tasks), style="dim"))
    console.print(max_line)

    # Update row
    is_hovered_update = hover == 1
    prefix2 = "▸ " if is_hovered_update else "  "
    update_line = Text(prefix2)
    if is_hovered_update:
        update_line.append(Text("update td", style="cyan bold"))
    else:
        update_line.append(Text("update td", style="dim"))
    console.print(update_line)

    if status_msg:
        console.print()
        console.print(Text(f"  {status_msg}", style="yellow bold"))

    # Hints
    if mode == "edit":
        hint_text = "  " + " │ ".join(["Esc:cancel", "Enter:confirm"])
    else:
        hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "e:edit", "Enter:select", "q:return"])
    console.print()
    console.print(Text("─" * DIVIDER_WIDTH, style="dim"))
    console.print(Text(hint_text, style="dim"))


def _run_settings_loop() -> None:
    hover = 0
    mode = "normal"
    edit_text = ""
    edit_cursor = 0
    status_msg = ""
    num_items = 2  # max_tasks, update

    while True:
        _render_settings(hover, mode, edit_text, edit_cursor, status_msg)
        key = term.read_key()

        if mode == "normal":
            status_msg = ""
            if key in ("q", term.KEY_ESC):
                break
            elif key in (term.KEY_ARROW_UP, "k"):
                if hover > 0:
                    hover -= 1
            elif key in (term.KEY_ARROW_DOWN, "j"):
                if hover < num_items - 1:
                    hover += 1
            elif key in (term.KEY_ENTER, "e"):
                if hover == 0:
                    mode = "edit"
                    edit_text = str(db.get_max_tasks())
                    edit_cursor = len(edit_text)
                elif hover == 1:
                    # Run update
                    import subprocess
                    result = subprocess.run(
                        ["uv", "tool", "upgrade", "td"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if result.returncode == 0:
                        status_msg = "✓ updated successfully"
                    else:
                        status_msg = f"✗ update failed: {result.stderr.strip().split(chr(10))[-1]}"

        elif mode == "edit":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                try:
                    new_max = int(edit_text)
                    if new_max < 1:
                        raise ValueError
                    db.set_max_tasks(new_max)
                    status_msg = f"✓ max tasks set to {new_max}"
                except ValueError:
                    status_msg = "✗ must be a positive integer"
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_BACKSPACE:
                if edit_cursor > 0:
                    edit_text = edit_text[:edit_cursor - 1] + edit_text[edit_cursor:]
                    edit_cursor -= 1
            elif key == term.KEY_DELETE:
                if edit_cursor < len(edit_text):
                    edit_text = edit_text[:edit_cursor] + edit_text[edit_cursor + 1:]
            elif key == term.KEY_ARROW_LEFT:
                if edit_cursor > 0:
                    edit_cursor -= 1
            elif key == term.KEY_ARROW_RIGHT:
                if edit_cursor < len(edit_text):
                    edit_cursor += 1
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif len(key) == 1 and key.isdigit():
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1


def run_settings() -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            _run_settings_loop()
        finally:
            term.show_cursor()


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