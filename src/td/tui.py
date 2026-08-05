from __future__ import annotations

import sys
import textwrap
from datetime import datetime, timezone
from functools import wraps

from rich.console import Console
from rich.text import Text

from . import db
from . import terminal as term

console = Console()

_VERSION: str | None = None


def _buffered_frame(render):
    """Render a complete terminal frame, then emit it with one write."""
    @wraps(render)
    def buffered(*args, **kwargs):
        with console.capture() as capture:
            render(*args, **kwargs)
        content = capture.get()
        if content.endswith("\n"):
            content = content[:-1]
        frame = "\033[H" + content + "\033[J"
        console.file.write(frame)
        console.file.flush()

    return buffered


def _app_version() -> str:
    """Return the installed package version, cached. Falls back to '?'."""
    global _VERSION
    if _VERSION is None:
        try:
            from importlib.metadata import version as _pkg_version
            _VERSION = _pkg_version("td-task")
        except Exception:
            _VERSION = "?"
    return _VERSION


def _footer_with_version(hint: str, width: int) -> Text:
    """Build a dim footer line with the app version right-aligned to width.

    Drops the version if the terminal is too narrow to fit it cleanly.
    """
    line = Text(hint, style="dim")
    ver = f"td v{_app_version()}"
    pad = width - len(hint) - len(ver)
    if pad >= 1:
        line.append(" " * pad)
        line.append(Text(ver, style="dim"))
    return line


def _copy_to_clipboard(text: str) -> bool:
    import subprocess
    import sys as _sys
    encoded = text.encode("utf-8")
    if _sys.platform == "darwin":
        candidates = [["pbcopy"]]
    elif _sys.platform == "win32":
        candidates = [["clip"]]
    else:
        candidates = [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]
    for cmd in candidates:
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            p.communicate(input=encoded)
            if p.returncode == 0:
                return True
        except FileNotFoundError:
            continue
        except Exception:
            break
    return False


def prompt_password(prompt_text: str = "Enter password: ") -> str:
    """Prompt the user for a password, masking the characters with *."""
    term.clear_screen()
    console.print()
    sys.stdout.write(f"  {prompt_text}")
    sys.stdout.flush()

    password = ""
    while True:
        key = term.read_key()
        if key in (term.KEY_ENTER, "\r", "\n"):
            break
        elif key in (term.KEY_ESC, "q"):
            term.show_cursor()
            sys.exit(0)
        elif key == term.KEY_BACKSPACE:
            if len(password) > 0:
                password = password[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif len(key) == 1 and ord(key) >= 32:
            password += key
            sys.stdout.write("*")
            sys.stdout.flush()

    term.clear_screen()
    return password


def _ensure_unlocked() -> bool:
    if not db.is_encryption_enabled():
        return True
    if db.ENCRYPTION_KEY is not None:
        return True

    attempts = 0
    while attempts < 3:
        if attempts == 0:
            prompt_text = "Database is encrypted. Enter password: "
        else:
            prompt_text = f"Incorrect password (attempt {attempts}/3). Try again: "
        password = prompt_password(prompt_text)
        if db.set_encryption_key_from_password(password):
            return True
        attempts += 1

    term.clear_screen()
    console.print(Text("  Too many incorrect password attempts. Exiting.", style="red bold"))
    sys.exit(1)


def _ensure_list_unlocked(list_name: str) -> bool:
    if not db.is_list_encryption_enabled(list_name) or db.is_list_unlocked(list_name):
        return True

    for attempt in range(3):
        if attempt == 0:
            prompt_text = f'List "{list_name}" is encrypted. Enter password: '
        else:
            prompt_text = f"Incorrect password (attempt {attempt}/3). Try again: "
        password = prompt_password(prompt_text)
        if db.set_list_encryption_key_from_password(list_name, password):
            return True

    term.clear_screen()
    console.print(Text(f'  Could not unlock list "{list_name}".', style="red bold"))
    return False


def _normal_hint_text(lock_list: bool = False) -> str:
    parts = ["a:task", "A:note", "e/Enter:edit", "E:rename note", "d:delete", "Space:done", "s:star", "c:clear"]
    if not lock_list:
        parts.append("l:view lists")
    parts.append("q:quit")
    parts.append("?:help")
    return "  " + " │ ".join(parts)


@_buffered_frame
def _render_help_screen(lock_list: bool = False) -> None:
    header = Text("help • ", style="bold")
    header.append(Text("keybindings & commands", style="dim"))
    console.print(header)
    
    # Calculate divider width dynamically
    divider_width = min(len(_normal_hint_text(lock_list)), console.width or 80)
    console.print(Text("─" * divider_width, style="dim"))
    console.print()

    # Group 1: Task Actions
    console.print(Text("Task & Note Actions:", style="bold yellow"))
    console.print("  a           Add a new task")
    console.print("  A           Add a Markdown note")
    console.print("  e / Enter   Edit selected task or note body")
    console.print("  E           Rename selected note")
    console.print("  d           Delete selected task")
    console.print("  Space       Toggle task done/active")
    console.print("  s           Toggle star/priority (pin to top)")
    console.print("  c           Archive all completed tasks")
    console.print("  y           Copy active tasks in list to clipboard")
    console.print()

    console.print(Text("Note Editor:", style="bold yellow"))
    console.print("  Esc         Save and close")
    console.print("  Ctrl+S      Save without closing")
    console.print("  Enter       Insert a new line")
    console.print("              Continue and indent Markdown bullets automatically")
    console.print("  PageUp/Down Move one viewport")
    console.print("  Alt+↑/↓     Move current line")
    clear_line_key = "Cmd+Backspace" if sys.platform == "darwin" else "Ctrl+Backspace"
    console.print(f"  {clear_line_key:<18}Clear current line")
    console.print("  Tab/Shift+Tab  Indent or outdent current line")
    console.print("  # / * / _   Headings, bullets, bold, and italic Markdown")
    console.print()

    # Group 2: Lists & Navigation
    console.print(Text("Lists & Navigation:", style="bold yellow"))
    console.print("  ↑/k  ↓/j    Navigate and scroll tasks / lists")
    console.print("  PageUp/Down  Move one viewport at a time")
    if not lock_list:
        console.print("  l / Tab     Open vertical Lists Menu")
        console.print("  Ctrl+P      Open 'go to list' fuzzy search dialog")
    console.print("  Ctrl+↑/↓    Reorder task position")
    console.print("  Alt+↑/↓     Duplicate task")
    console.print()

    if not lock_list:
        # Group 3: Lists Menu Actions (when inside Lists Menu)
        console.print(Text("Lists Menu Actions:", style="bold yellow"))
        console.print("  Enter       Open highlighted list and return to tasks")
        console.print("  Esc / q     Quit application")
        console.print("  a           Add a new list inline")
        console.print("  e           Rename highlighted list inline")
        console.print("  A           Archive highlighted list")
        console.print("  ,           View and restore archived lists")
        console.print("  d           Delete highlighted list with all tasks inside")
        console.print("  Shift+↑/↓   Reorder highlighted list position")
        console.print()

    # Group 4: Screens & App
    console.print(Text("Screens & App:", style="bold yellow"))
    console.print("  ,           View archived tasks")
    console.print("  /           Open settings preferences")
    console.print("  q / Esc     Exit help screen / Quit application")
    console.print()

    console.print(Text("─" * divider_width, style="dim"))
    console.print(_footer_with_version("  Press any key to return...", divider_width))


def _task_visible_rows(mode: str, status_msg: str, term_height: int) -> int:
    """Return task rows that fit above the footer and transient messages."""
    reserved_rows = 2 if mode in ("new_note", "confirm") or status_msg else 0
    return max(1, term_height - 6 - reserved_rows)


def _fuzzy_visible_rows(term_height: int) -> int:
    """Return rows available beneath the fuzzy-list query."""
    return max(1, term_height - 9)


def _page_index(index: int, count: int, page_size: int, direction: int) -> int:
    """Move an index by one page while keeping it inside the collection."""
    if count <= 0:
        return 0
    step = max(1, page_size)
    return max(0, min(count - 1, index + direction * step))


def _task_visual_row_ranges(
    tasks: list[dict],
    hover: int,
    divider_width: int,
    mode: str = "normal",
) -> tuple[list[int], list[int], int]:
    """Return each task's visual row range and the total rendered rows."""
    wrap_width = max(20, divider_width - 4)
    starts: list[int] = []
    ends: list[int] = []
    total_rows = 0
    previous_starred = False

    for index, task in enumerate(tasks):
        if index > 0 and previous_starred:
            total_rows += 1

        starts.append(total_rows)
        if mode == "edit" and index == hover:
            row_count = 1
        else:
            row_count = max(1, len(textwrap.wrap(task.get("text", ""), width=wrap_width)))
        total_rows += row_count
        ends.append(total_rows)
        previous_starred = task.get("starred", 0) == 1

    return starts, ends, total_rows


def _task_page_hover(
    tasks: list[dict],
    hover: int,
    divider_width: int,
    visible_rows: int,
    direction: int,
) -> int:
    """Move task selection by roughly one viewport of rendered rows."""
    if not tasks:
        return 0
    starts, _, _ = _task_visual_row_ranges(tasks, hover, divider_width)
    target_row = starts[hover] + direction * max(1, visible_rows)

    if direction > 0:
        for index in range(hover + 1, len(tasks)):
            if starts[index] >= target_row:
                return index
        return len(tasks) - 1

    for index in range(hover - 1, -1, -1):
        if starts[index] <= target_row:
            return index
    return 0


@_buffered_frame
def _render_main(
    tasks: list[dict],
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    edit_cursor: int = 0,
    confirm_msg: str = "",
    list_name: str = "main",
    lock_list: bool = False,
    view: str = "tasks",
    status_msg: str = "",
    lists_scroll: int = 0,
    tasks_scroll: int = 0,
    fuzzy_scroll: int = 0,
) -> None:
    divider_width = min(len(_normal_hint_text(lock_list)), console.width or 80)

    if view == "lists_menu":
        lists = db.get_all_lists()
        header = Text("td • ", style="bold")
        header.append(Text("lists menu", style="bold cyan"))
        header.append(Text(f" • {len(lists)} lists", style="dim"))
        console.print(header, end="\033[K\n")
    else:
        open_count = sum(1 for t in tasks if t["status"] == "active")
        completed_count = db.get_completed_count(list_name)
        header = Text("td • ", style="bold")
        header.append(Text(f"{list_name}", style="bold cyan"))
        header.append(Text(" • ", style="dim"))
        header.append(Text(f"{open_count} open", style="dim"))
        header.append(Text(" / ", style="dim"))
        header.append(Text(f"{completed_count} completed", style="dim"))
        console.print(header, end="\033[K\n")

    # Determine hints
    if mode == "edit":
        if view == "lists_menu":
            hint_parts = ["Esc:cancel", "Enter:confirm rename"]
        else:
            hint_parts = ["Esc:cancel", "Enter:confirm edit"]
    elif mode == "new_list":
        hint_parts = ["Esc:cancel", "Enter:create list"]
    elif mode == "new_note":
        hint_parts = ["Esc:cancel", "Enter:create note"]
    elif mode == "confirm":
        hint_parts = ["Enter:confirm", "Esc:cancel"]
    elif mode == "fuzzy_list":
        hint_parts = ["Esc:cancel", "Enter:go to list", "↑/↓:navigate", "PgUp/PgDn:page"]
    else:
        # mode == "normal"
        if view == "lists_menu":
            hint_parts = [
                "PgUp/PgDn:page", "a:add", "e:edit", "A:archive", ",:archived", "d:delete",
                "Enter:open", "q:quit",
            ]
        else:
            hint_parts = ["PgUp/PgDn:page", "a:task", "A:note", "e/Enter:edit", "E:rename note", "d:delete", "Space:done", "s:star", "c:clear"]
            if not lock_list:
                hint_parts.append("l:view lists")
            hint_parts.append("q:quit")
            hint_parts.append("?:help")

    hint_text = "  " + " │ ".join(hint_parts)

    console.print(Text("─" * divider_width, style="dim"), end="\033[K\n")
    console.print(end="\033[K\n")

    # Fuzzy List search overlay rendering
    if mode == "fuzzy_list":
        console.print(Text("  Go to list:", style="bold yellow"), end="\033[K\n")
        query_line = Text("  > ", style="yellow bold")
        query_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        query_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            query_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
        console.print(query_line, end="\033[K\n")
        console.print(Text("  " + "─" * (divider_width - 2), style="dim"), end="\033[K\n")
        
        all_lists = db.get_all_lists()
        matched = []
        q_lower = edit_text.lower()
        for lst in all_lists:
            lst_lower = lst.lower()
            if not q_lower:
                matched.append(lst)
            elif q_lower in lst_lower:
                matched.append(lst)
            else:
                idx = 0
                match = True
                for char in q_lower:
                    idx = lst_lower.find(char, idx)
                    if idx == -1:
                        match = False
                        break
                    idx += 1
                if match:
                    matched.append(lst)
                    
        if not matched:
            console.print(Text("    No matching lists. Press Enter to create new list.", style="dim"), end="\033[K\n")
            visible_count = 1
        else:
            visible_rows = _fuzzy_visible_rows(console.height or 24)
            visible_matches = matched[fuzzy_scroll:fuzzy_scroll + visible_rows]
            for idx, match_item in enumerate(visible_matches, start=fuzzy_scroll):
                is_selected = idx == hover
                prefix = "  ▸ " if is_selected else "    "
                if is_selected:
                    console.print(Text(f"{prefix}{match_item}", style="bold cyan"), end="\033[K\n")
                else:
                    console.print(Text(f"{prefix}{match_item}", style="dim"), end="\033[K\n")
            visible_count = len(visible_matches)
        visible_rows = _fuzzy_visible_rows(console.height or 24)
        for _ in range(visible_rows - visible_count):
            console.print(end="\033[K\n")
    elif view == "lists_menu":
        lists = db.get_all_lists()
        term_height = console.height or 24
        max_visible = _task_visible_rows(mode, status_msg, term_height)
        list_slots = max(0, max_visible - (1 if mode == "new_list" else 0))
        start = lists_scroll
        end = min(start + list_slots, len(lists))

        lines = []
        for i in range(start, end):
            lst = lists[i]
            is_hovered = i == hover
            prefix = "▸ " if is_hovered else "  "

            if mode == "edit" and is_hovered:
                edit_style = "bold cyan"
                cursor_style = "reverse bold cyan"
                edit_line = Text()
                edit_line.append(Text(edit_text[:edit_cursor], style=edit_style))
                char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
                edit_line.append(Text(char_under, style=cursor_style))
                if edit_cursor < len(edit_text):
                    edit_line.append(Text(edit_text[edit_cursor + 1:], style=edit_style))

                line = Text(prefix)
                line.append(edit_line)
                lines.append(line)
            else:
                lock_suffix = " 🔒" if db.is_list_encryption_enabled(lst) else ""
                if is_hovered:
                    lines.append(Text(f"▸ {lst}{lock_suffix}", style="bold cyan"))
                else:
                    lines.append(Text(f"  {lst}{lock_suffix}"))

        if mode == "new_list":
            prefix = "▸ "
            edit_style = "bold cyan"
            cursor_style = "reverse bold cyan"
            edit_line = Text()
            edit_line.append(Text(edit_text[:edit_cursor], style=edit_style))
            char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
            edit_line.append(Text(char_under, style=cursor_style))
            if edit_cursor < len(edit_text):
                edit_line.append(Text(edit_text[edit_cursor + 1:], style=edit_style))

            line = Text(prefix)
            line.append(edit_line)
            lines.append(line)

        if not lists and mode != "new_list":
            lines.append(Text("  No lists. Press a to add one.", style="dim"))

        visible_lines = lines[:max_visible]
        for line in visible_lines:
            console.print(line, end="\033[K\n")
        for _ in range(max_visible - len(visible_lines)):
            console.print(end="\033[K\n")
    else:
        lines = []
        prev_starred = False
        for i, task in enumerate(tasks):
            is_hovered = i == hover
            is_done = task["status"] == "done"
            is_starred = task.get("starred", 0) == 1
            is_note = task.get("is_note", False)

            if i > 0 and prev_starred and not is_starred:
                lines.append(Text(""))

            prefix = "▸ " if is_hovered else "  "
            marker = "★" if is_starred else ("✓" if is_done else "○")

            if mode == "edit" and i == hover:
                edit_style = "bold yellow" if is_starred else "cyan bold"
                cursor_style = "reverse bold yellow" if is_starred else "reverse cyan bold"
                if is_note:
                    edit_style += " underline"
                    cursor_style += " underline"
                
                edit_line = Text()
                edit_line.append(Text(edit_text[:edit_cursor], style=edit_style))
                char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
                edit_line.append(Text(char_under, style=cursor_style))
                if edit_cursor < len(edit_text):
                    edit_line.append(Text(edit_text[edit_cursor + 1:], style=edit_style))
                
                line = Text(prefix)
                if is_starred:
                    line.append(Text(marker, style="bold yellow"))
                else:
                    line.append(marker)
                line.append(" ")
                line.append(edit_line)
                lines.append(line)
            else:
                text = task["text"]
                if not text:
                    line_text = Text(" ", style="underline dim")
                elif is_done:
                    line_text = Text(text, style="strike dim underline" if is_note else "strike dim")
                elif is_hovered:
                    if is_starred:
                        line_text = Text(text, style="bold yellow underline" if is_note else "bold yellow")
                    else:
                        line_text = Text(text, style="cyan bold underline" if is_note else "cyan bold")
                else:
                    if is_starred:
                        line_text = Text(text, style="bold yellow underline" if is_note else "bold yellow")
                    else:
                        line_text = Text(text, style="underline" if is_note else None)

                # Word wrapping aligned with marker width (4 chars)
                wrap_w = max(20, divider_width - 4)
                import textwrap
                wrapped_text_lines = textwrap.wrap(line_text.plain, width=wrap_w)
                
                if not wrapped_text_lines:
                    line = Text(prefix)
                    if is_starred:
                        line.append(Text(marker, style="bold yellow"))
                    else:
                        line.append(marker)
                    line.append(" ")
                    line.append(line_text)
                    lines.append(line)
                else:
                    for line_idx, w_line in enumerate(wrapped_text_lines):
                        w_text_obj = Text(w_line)
                        if is_done:
                            w_text_obj.style = "strike dim underline" if is_note else "strike dim"
                        elif is_hovered:
                            if is_starred:
                                w_text_obj.style = "bold yellow underline" if is_note else "bold yellow"
                            else:
                                w_text_obj.style = "cyan bold underline" if is_note else "cyan bold"
                        elif is_starred:
                            w_text_obj.style = "bold yellow underline" if is_note else "bold yellow"
                        elif is_note:
                            w_text_obj.style = "underline"
                        
                        if line_idx == 0:
                            line = Text(prefix)
                            if is_starred:
                                line.append(Text(marker, style="bold yellow"))
                            else:
                                line.append(marker)
                            line.append(" ")
                            line.append(w_text_obj)
                        else:
                            line = Text("    ")
                            line.append(w_text_obj)
                        lines.append(line)
                        
            prev_starred = is_starred

        if not tasks:
            lines.append(Text("  No items. Press a for a task or A for a note.", style="dim"))

        visible_rows = _task_visible_rows(mode, status_msg, console.height or 24)
        visible_lines = lines[tasks_scroll:tasks_scroll + visible_rows]
        for line in visible_lines:
            console.print(line, end="\033[K\n")
        for _ in range(visible_rows - len(visible_lines)):
            console.print(end="\033[K\n")

    if mode == "new_note":
        console.print(end="\033[K\n")
        console.print(Text("  Note name", style="bold yellow"), end="\033[K\n")
        input_line = Text("  > ", style="yellow bold")
        input_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        input_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            input_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
        console.print(input_line, end="\033[K\n")
    elif mode == "confirm":
        console.print(end="\033[K\n")
        console.print(Text(f"  {confirm_msg}", style="yellow bold"), end="\033[K\n")
    elif status_msg:
        console.print(end="\033[K\n")
        console.print(Text(f"  {status_msg}", style="dim"), end="\033[K\n")

    console.print(end="\033[K\n")
    console.print(Text("─" * divider_width, style="dim"), end="\033[K\n")
    console.print(
        Text(hint_text, style="dim"),
        end="\033[K\n",
        overflow="crop",
        no_wrap=True,
    )


def _fmt_timestamp(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _default_note_title() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _markdown_preview_line(source: str) -> Text:
    """Render supported inline Markdown for a non-active editor line."""
    import re

    heading = re.match(r"^\s*#{1,6}\s+(.*)$", source)
    if heading:
        source = heading.group(1)
        base_style = "bold"
        prefix = ""
    else:
        base_style = ""
        bullet = re.match(r"^(\s*)[*+-]\s+(.*)$", source)
        if bullet:
            prefix = f"{bullet.group(1)}• "
            source = bullet.group(2)
        else:
            prefix = ""

    rendered = Text(prefix, style=base_style)
    token = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_)")
    cursor = 0
    for match in token.finditer(source):
        rendered.append(source[cursor:match.start()], style=base_style)
        value = match.group(0)
        if value.startswith("_"):
            style = "italic"
            inner = value[1:-1]
        elif value.startswith("**"):
            style = "bold"
            inner = value[2:-2]
        else:
            style = "bold"
            inner = value[1:-1]
        if base_style and base_style not in style:
            style = f"{base_style} {style}"
        rendered.append(inner, style=style)
        cursor = match.end()
    rendered.append(source[cursor:], style=base_style)
    return rendered


def _bullet_line_parts(source: str) -> tuple[str, str, str] | None:
    import re

    match = re.match(r"^(\s*)([*+-])\s(.*)$", source)
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3)


def _wrap_editor_text(source: Text, width: int) -> list[Text]:
    """Soft-wrap styled text without changing or dropping source characters."""
    from rich.cells import cell_len

    width = max(1, width)
    plain = source.plain
    if not plain:
        return [Text()]

    offsets: list[tuple[int, int]] = []
    start = 0
    while start < len(plain):
        end = start
        used = 0
        last_break: int | None = None
        has_content = False

        while end < len(plain):
            char_width = cell_len(plain[end])
            if end > start and used + char_width > width:
                break
            used += char_width
            end += 1
            if plain[end - 1].isspace() and has_content:
                last_break = end
            elif not plain[end - 1].isspace():
                has_content = True
            if used >= width:
                break

        if end < len(plain) and last_break is not None and last_break > start:
            end = last_break
        if end == start:
            end += 1

        offsets.append((start, end))
        start = end

    return [source[start:end] for start, end in offsets]


def _note_editor_visual_rows(
    lines: list[str],
    active_row: int,
    column: int,
    content_width: int,
) -> tuple[list[tuple[int, int, Text]], int]:
    """Build wrapped display rows and return the active cursor row index."""
    visual_rows: list[tuple[int, int, Text]] = []
    cursor_visual_row = 0

    for line_index, line in enumerate(lines):
        if line_index == active_row:
            rendered = Text(line, style="cyan bold")
            if column < len(line):
                rendered.stylize("reverse cyan bold", column, column + 1)
            else:
                rendered.append(" ", style="reverse cyan bold")
            wrapped = _wrap_editor_text(rendered, content_width)
        else:
            wrapped = _wrap_editor_text(_markdown_preview_line(line), content_width)

        for segment_index, segment in enumerate(wrapped):
            visual_rows.append((line_index, segment_index, segment))
            if line_index == active_row and any(
                "reverse" in str(span.style) for span in segment.spans
            ):
                cursor_visual_row = len(visual_rows) - 1

    return visual_rows, cursor_visual_row


def _page_note_cursor(
    lines: list[str],
    row: int,
    column: int,
    content_width: int,
    visible_rows: int,
    direction: int,
) -> tuple[int, int]:
    """Move the editor cursor by one viewport of wrapped visual rows."""
    visual_rows, cursor_visual_row = _note_editor_visual_rows(
        lines, row, column, content_width
    )
    if not visual_rows:
        return row, column

    target_visual_row = max(
        0,
        min(
            len(visual_rows) - 1,
            cursor_visual_row + direction * max(1, visible_rows),
        ),
    )
    target_row, target_segment, _ = visual_rows[target_visual_row]

    if target_row != row:
        return target_row, min(column, len(lines[target_row]))

    active_segments = [
        segment
        for line_index, _, segment in visual_rows
        if line_index == row
    ]
    current_segment = visual_rows[cursor_visual_row][1]
    current_start = sum(len(segment.plain) for segment in active_segments[:current_segment])
    target_start = sum(len(segment.plain) for segment in active_segments[:target_segment])
    horizontal_offset = max(0, column - current_start)
    return row, min(len(lines[row]), target_start + horizontal_offset)


@_buffered_frame
def _render_note_editor(
    title: str,
    lines: list[str],
    row: int,
    column: int,
    scroll: int,
    status_msg: str = "",
) -> None:
    width = max(30, console.width or 80)
    height = max(10, console.height or 24)

    header = Text("note • ", style="bold")
    header.append(Text(title, style="bold cyan underline"))
    header.append(Text(f" • line {row + 1}/{len(lines)}", style="dim"))
    console.print(header, end="\033[K\n", overflow="crop", no_wrap=True)
    console.print(Text("─" * width, style="dim"), end="\033[K\n")

    visible_rows = max(3, height - 6)
    number_width = max(2, len(str(len(lines))))
    content_width = max(10, width - number_width - 5)
    visual_rows, _ = _note_editor_visual_rows(lines, row, column, content_width)
    visible = visual_rows[scroll:scroll + visible_rows]

    for line_index, segment_index, segment in visible:
        if segment_index == 0:
            prefix = f"{'▸' if line_index == row else ' '} {line_index + 1:>{number_width}} │ "
        else:
            prefix = f"  {'':>{number_width}} │ "
        output = Text(prefix, style="cyan bold" if line_index == row else "dim")
        output.append(segment)
        console.print(output, end="\033[K\n", overflow="crop", no_wrap=True)

    for _ in range(visible_rows - len(visible)):
        console.print(end="\033[K\n")

    footer = "  Esc:save & close │ Ctrl+S:save │ Enter:new line │ arrows:move │ PgUp/PgDn:page"
    if status_msg:
        footer = f"  {status_msg} │ " + footer.strip()
    clear_line_key = "Cmd+⌫" if sys.platform == "darwin" else "Ctrl+⌫"
    editor_hint = (
        f"  Alt+↑/↓:move line │ {clear_line_key}:clear line │ "
        "Tab/Shift+Tab:indent/outdent"
    )
    console.print(Text("─" * width, style="dim"), end="\033[K\n")
    console.print(Text(footer, style="dim"), end="\033[K\n", overflow="crop", no_wrap=True)
    console.print(Text(editor_hint, style="dim"), end="\033[K\n", overflow="crop", no_wrap=True)


def _run_note_editor(note_id: int) -> None:
    note = db.get_note(note_id)
    if note is None:
        return
    lines = note["content"].split("\n") or [""]
    row = 0
    column = 0
    scroll = 0
    status_msg = ""

    while True:
        visible_rows = max(3, (console.height or 24) - 6)
        width = max(30, console.width or 80)
        number_width = max(2, len(str(len(lines))))
        content_width = max(10, width - number_width - 5)
        _, cursor_visual_row = _note_editor_visual_rows(lines, row, column, content_width)
        if cursor_visual_row < scroll:
            scroll = cursor_visual_row
        elif cursor_visual_row >= scroll + visible_rows:
            scroll = cursor_visual_row - visible_rows + 1
        _render_note_editor(note["title"], lines, row, column, scroll, status_msg)
        status_msg = ""
        key = term.read_key()

        if key == term.KEY_ESC:
            db.update_note_content(note_id, "\n".join(lines))
            term.clear_screen()
            return
        if key == term.KEY_CTRL_S:
            db.update_note_content(note_id, "\n".join(lines))
            status_msg = "saved"
        elif key == term.KEY_ALT_ARROW_UP:
            if row > 0:
                lines[row - 1], lines[row] = lines[row], lines[row - 1]
                row -= 1
        elif key == term.KEY_ALT_ARROW_DOWN:
            if row < len(lines) - 1:
                lines[row], lines[row + 1] = lines[row + 1], lines[row]
                row += 1
        elif key in (term.KEY_ALT_ARROW_LEFT, term.KEY_ALT_WORD_LEFT):
            while column > 0 and lines[row][column - 1].isspace():
                column -= 1
            while column > 0 and not lines[row][column - 1].isspace():
                column -= 1
        elif key in (term.KEY_ALT_ARROW_RIGHT, term.KEY_ALT_WORD_RIGHT):
            line_length = len(lines[row])
            while column < line_length and not lines[row][column].isspace():
                column += 1
            while column < line_length and lines[row][column].isspace():
                column += 1
        elif key in (term.KEY_ALT_BACKSPACE, term.KEY_ALT_BACKSPACE_BS):
            word_start = column
            while word_start > 0 and lines[row][word_start - 1].isspace():
                word_start -= 1
            while word_start > 0 and not lines[row][word_start - 1].isspace():
                word_start -= 1
            lines[row] = lines[row][:word_start] + lines[row][column:]
            column = word_start
        elif key in (term.KEY_CMD_BACKSPACE, term.KEY_CTRL_BACKSPACE):
            lines[row] = ""
            column = 0
        elif key == term.KEY_PAGE_UP:
            row, column = _page_note_cursor(
                lines, row, column, content_width, visible_rows, -1
            )
            visual_rows, cursor_visual_row = _note_editor_visual_rows(
                lines, row, column, content_width
            )
            scroll = min(
                cursor_visual_row, max(0, len(visual_rows) - visible_rows)
            )
        elif key == term.KEY_PAGE_DOWN:
            row, column = _page_note_cursor(
                lines, row, column, content_width, visible_rows, 1
            )
            visual_rows, cursor_visual_row = _note_editor_visual_rows(
                lines, row, column, content_width
            )
            scroll = min(
                cursor_visual_row, max(0, len(visual_rows) - visible_rows)
            )
        elif key == term.KEY_ARROW_UP:
            if row > 0:
                row -= 1
                column = min(column, len(lines[row]))
        elif key == term.KEY_ARROW_DOWN:
            if row < len(lines) - 1:
                row += 1
                column = min(column, len(lines[row]))
        elif key == term.KEY_ARROW_LEFT:
            if column > 0:
                column -= 1
            elif row > 0:
                row -= 1
                column = len(lines[row])
        elif key == term.KEY_ARROW_RIGHT:
            if column < len(lines[row]):
                column += 1
            elif row < len(lines) - 1:
                row += 1
                column = 0
        elif key == term.KEY_HOME:
            column = 0
        elif key == term.KEY_END:
            column = len(lines[row])
        elif key == term.KEY_ENTER:
            bullet = _bullet_line_parts(lines[row])
            if bullet and not bullet[2].strip():
                lines[row] = ""
                column = 0
            else:
                remainder = lines[row][column:]
                lines[row] = lines[row][:column]
                if bullet:
                    indent, marker, _ = bullet
                    continuation_indent = indent if indent else "  "
                    prefix = f"{continuation_indent}{marker} "
                    remainder = prefix + remainder
                    column = len(prefix)
                else:
                    column = 0
                lines.insert(row + 1, remainder)
                row += 1
        elif key == term.KEY_BACKSPACE:
            bullet = _bullet_line_parts(lines[row])
            if bullet and not bullet[2].strip():
                lines[row] = ""
                column = 0
            elif column > 0:
                lines[row] = lines[row][:column - 1] + lines[row][column:]
                column -= 1
            elif row > 0:
                previous_length = len(lines[row - 1])
                lines[row - 1] += lines.pop(row)
                row -= 1
                column = previous_length
        elif key == term.KEY_DELETE:
            if column < len(lines[row]):
                lines[row] = lines[row][:column] + lines[row][column + 1:]
            elif row < len(lines) - 1:
                lines[row] += lines.pop(row + 1)
        elif key == "\t":
            lines[row] = "  " + lines[row]
            column += 2
        elif key == term.KEY_SHIFT_TAB:
            if lines[row].startswith("\t"):
                remove_count = 1
            else:
                remove_count = min(2, len(lines[row]) - len(lines[row].lstrip(" ")))
            lines[row] = lines[row][remove_count:]
            column = max(0, column - remove_count)
        elif len(key) == 1 and ord(key) >= 32:
            lines[row] = lines[row][:column] + key + lines[row][column:]
            column += 1


@_buffered_frame
def _render_archive(
    tasks: list[dict],
    hover: int,
    scroll: int,
    term_height: int,
    mode: str = "normal",
    confirm_msg: str = "",
    list_name: str = "main",
) -> None:
    header = Text(f"archive • {list_name} • ", style="bold")
    header.append(Text(f"{len(tasks)} items", style="dim"))
    console.print(header)

    if mode == "confirm":
        hint_text = "  " + " │ ".join(["Enter:confirm", "Esc:cancel"])
    else:
        hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "PgUp/PgDn:page", "d:delete", "r:restore", "c:clear", "q:return"])

    divider_width = min(len(_normal_hint_text()), console.width or 80)
    console.print(Text("─" * divider_width, style="dim"))
    console.print()

    max_lines = max(1, term_height - 6 - (2 if mode == "confirm" else 0))
    rendered_lines = 0
    if not tasks:
        console.print(Text("  No archived items.", style="dim"))
        rendered_lines = 1
    else:
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
            name_style = "strike bold cyan" if is_hovered else "strike dim"
            if task.get("is_note"):
                name_style += " underline"
            if is_hovered:
                line.append(Text(task["text"], style=name_style))
                line.append(Text(f"  {ts_text}", style="strike dim"))
            else:
                line.append(Text(task["text"], style=name_style))
                line.append(Text(f"  {ts_text}", style="strike dim"))
            console.print(line)
            rendered_lines += 1

    for _ in range(max_lines - rendered_lines):
        console.print(end="\033[K\n")

    if mode == "confirm":
        console.print()
        console.print(Text(f"  {confirm_msg}", style="yellow bold"))

    console.print()
    console.print(Text("─" * divider_width, style="dim"))
    console.print(Text(hint_text, style="dim"), overflow="crop", no_wrap=True)


@_buffered_frame
def _render_archived_lists(
    lists: list[dict],
    hover: int,
    scroll: int = 0,
    mode: str = "normal",
    confirm_msg: str = "",
) -> None:
    width = min(console.width or 80, 100)

    header = Text("lists archive • ", style="bold")
    header.append(Text(f"{len(lists)} lists", style="dim"))
    console.print(header, end="\033[K\n")
    console.print(Text("─" * width, style="dim"), end="\033[K\n")
    console.print(end="\033[K\n")

    visible_rows = max(1, (console.height or 24) - 6 - (2 if mode == "confirm" else 0))
    rendered_rows = 0
    if not lists:
        console.print(Text("  No archived lists.", style="dim"), end="\033[K\n")
        rendered_rows = 1
    else:
        start = scroll
        end = min(len(lists), start + visible_rows)
        for index in range(start, end):
            archived_list = lists[index]
            selected = index == hover
            prefix = "▸ " if selected else "  "
            style = "strike bold cyan" if selected else "strike dim"
            line = Text(prefix)
            line.append(Text(archived_list["name"], style=style))
            if db.is_list_encryption_enabled(archived_list["name"]):
                line.append(Text(" 🔒", style="dim"))
            archived_at = _fmt_timestamp(archived_list["archived_at"])
            line.append(Text(f"  archived {archived_at}", style="dim"))
            console.print(line, end="\033[K\n")
            rendered_rows += 1

    for _ in range(visible_rows - rendered_rows):
        console.print(end="\033[K\n")

    if mode == "confirm":
        console.print(end="\033[K\n")
        console.print(Text(f"  {confirm_msg}", style="yellow bold"), end="\033[K\n")

    console.print(end="\033[K\n")
    console.print(Text("─" * width, style="dim"), end="\033[K\n")
    if mode == "confirm":
        hint = "  Enter:confirm permanent delete │ Esc:cancel"
    else:
        hint = "  Enter/r:restore │ d:delete permanently │ ↑/↓:navigate │ PgUp/PgDn:page │ q:return"
    console.print(
        Text(hint, style="dim"),
        end="\033[K\n",
        overflow="crop",
        no_wrap=True,
    )


def _run_archived_lists_loop() -> None:
    hover = 0
    scroll = 0
    mode = "normal"
    confirm_name = ""

    while True:
        lists = db.get_archived_lists()
        if lists:
            hover = min(hover, len(lists) - 1)
            visible_rows = max(
                1, (console.height or 24) - 6 - (2 if mode == "confirm" else 0)
            )
            if hover < scroll:
                scroll = hover
            elif hover >= scroll + visible_rows:
                scroll = hover - visible_rows + 1
            scroll = max(0, min(scroll, max(0, len(lists) - visible_rows)))
        else:
            hover = 0
            scroll = 0
        confirm_msg = (
            f'Delete archived list "{confirm_name}" and all its items permanently?'
            if mode == "confirm"
            else ""
        )
        _render_archived_lists(lists, hover, scroll, mode, confirm_msg)
        key = term.read_key()

        if mode == "confirm":
            if key in (term.KEY_ENTER, "y"):
                db.delete_list(confirm_name)
            mode = "normal"
            confirm_name = ""
            continue

        if key in ("q", term.KEY_ESC):
            return
        if key in (term.KEY_ARROW_UP, "k"):
            hover = max(0, hover - 1)
        elif key in (term.KEY_ARROW_DOWN, "j"):
            if hover < len(lists) - 1:
                hover += 1
        elif key == term.KEY_PAGE_UP:
            hover = _page_index(
                hover, len(lists), max(1, (console.height or 24) - 6), -1
            )
            scroll = hover
        elif key == term.KEY_PAGE_DOWN:
            hover = _page_index(
                hover, len(lists), max(1, (console.height or 24) - 6), 1
            )
            scroll = hover
        elif key in (term.KEY_ENTER, "r"):
            if lists:
                db.restore_list(lists[hover]["name"])
        elif key == "d":
            if lists:
                confirm_name = lists[hover]["name"]
                mode = "confirm"


def _run_main_loop(list_name: str = "main", lock_list: bool = False) -> None:
    hover = 0
    mode = "normal"
    active_lists = db.get_all_lists()
    view = "lists_menu" if not active_lists and not lock_list else "tasks"
    edit_task_id: int | None = None
    edit_note_id: int | None = None
    edit_text = ""
    edit_cursor = 0
    confirm_action: str = ""  # task and list confirmation action
    confirm_task_id: int | None = None
    confirm_list_name = ""
    status_msg = ""
    lists_scroll = 0
    tasks_scroll = 0
    fuzzy_scroll = 0

    current_list = list_name
    if not lock_list and active_lists and current_list not in active_lists:
        current_list = active_lists[0]

    while True:
        if mode == "help":
            term.clear_screen()
            _render_help_screen(lock_list)
            term.read_key()
            term.clear_screen()
            mode = "normal"
            continue

        if view == "tasks" and not _ensure_list_unlocked(current_list):
            if lock_list:
                return
            view = "lists_menu"
            hover = 0
            continue

        tasks = db.get_active_tasks(current_list) if view == "tasks" else []
        
        # Determine and clamp hovers
        if mode == "fuzzy_list":
            all_lists = db.get_all_lists()
            matched = []
            q_lower = edit_text.lower()
            for lst in all_lists:
                lst_lower = lst.lower()
                if not q_lower or q_lower in lst_lower:
                    matched.append(lst)
                else:
                    idx = 0
                    match = True
                    for char in q_lower:
                        idx = lst_lower.find(char, idx)
                        if idx == -1:
                            match = False
                            break
                        idx += 1
                    if match:
                        matched.append(lst)
            if matched and hover >= len(matched):
                hover = len(matched) - 1
            if not matched:
                hover = 0
                fuzzy_scroll = 0
            else:
                fuzzy_rows = _fuzzy_visible_rows(console.height or 24)
                if hover < fuzzy_scroll:
                    fuzzy_scroll = hover
                elif hover >= fuzzy_scroll + fuzzy_rows:
                    fuzzy_scroll = hover - fuzzy_rows + 1
                fuzzy_scroll = max(
                    0, min(fuzzy_scroll, max(0, len(matched) - fuzzy_rows))
                )
        elif view == "lists_menu":
            lists = db.get_all_lists()
            if lists and hover >= len(lists):
                hover = len(lists) - 1
            if not lists:
                hover = 0
            max_vis = _task_visible_rows(mode, status_msg, console.height or 24)
            if hover < lists_scroll:
                lists_scroll = hover
            elif hover >= lists_scroll + max_vis:
                lists_scroll = hover - max_vis + 1
        else:
            if tasks and hover >= len(tasks):
                hover = len(tasks) - 1
            if not tasks:
                hover = 0
                tasks_scroll = 0
            else:
                divider_width = min(len(_normal_hint_text(lock_list)), console.width or 80)
                starts, ends, total_rows = _task_visual_row_ranges(
                    tasks, hover, divider_width, mode
                )
                visible_rows = _task_visible_rows(mode, status_msg, console.height or 24)
                if starts[hover] < tasks_scroll:
                    tasks_scroll = starts[hover]
                if ends[hover] > tasks_scroll + visible_rows:
                    tasks_scroll = ends[hover] - visible_rows
                tasks_scroll = max(0, min(tasks_scroll, max(0, total_rows - visible_rows)))

        # Construct confirmation message
        if mode == "confirm" and confirm_action == "archive":
            confirm_msg = "Clear all done tasks?"
        elif mode == "confirm" and confirm_action == "delete":
            task_text = next((t["text"] for t in tasks if t["id"] == confirm_task_id), "")
            confirm_msg = f'Delete "{task_text}"?'
        elif mode == "confirm" and confirm_action == "delete_list":
            confirm_msg = f'Delete list "{confirm_list_name}"? All tasks inside will be permanently lost!'
        elif mode == "confirm" and confirm_action == "archive_list":
            confirm_msg = f'Archive list "{confirm_list_name}"? Its items will be preserved.'
        else:
            confirm_msg = ""

        _render_main(
            tasks,
            hover,
            mode,
            edit_text,
            edit_cursor,
            confirm_msg,
            current_list,
            lock_list,
            view,
            status_msg,
            lists_scroll,
            tasks_scroll,
            fuzzy_scroll,
        )
        status_msg = ""

        key = term.read_key()

        # Fuzzy list mode logic
        if mode == "fuzzy_list":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
                hover = 0
                fuzzy_scroll = 0
            elif key == term.KEY_ARROW_UP:
                if hover > 0:
                    hover -= 1
            elif key == term.KEY_ARROW_DOWN:
                if matched and hover < len(matched) - 1:
                    hover += 1
            elif key == term.KEY_PAGE_UP:
                hover = _page_index(
                    hover, len(matched), _fuzzy_visible_rows(console.height or 24), -1
                )
                fuzzy_scroll = hover
            elif key == term.KEY_PAGE_DOWN:
                hover = _page_index(
                    hover, len(matched), _fuzzy_visible_rows(console.height or 24), 1
                )
                fuzzy_scroll = hover
            elif key == term.KEY_BACKSPACE:
                if edit_cursor > 0:
                    edit_text = edit_text[:edit_cursor - 1] + edit_text[edit_cursor:]
                    edit_cursor -= 1
            elif key == term.KEY_DELETE:
                if edit_cursor < len(edit_text):
                    edit_text = edit_text[:edit_cursor] + edit_text[edit_cursor + 1:]
            elif key == term.KEY_ARROW_LEFT:
                edit_cursor = max(0, edit_cursor - 1)
            elif key == term.KEY_ARROW_RIGHT:
                edit_cursor = min(len(edit_text), edit_cursor + 1)
            elif key == term.KEY_ENTER:
                if matched:
                    current_list = matched[hover]
                else:
                    cleaned_name = edit_text.strip()
                    if cleaned_name:
                        db.create_list(cleaned_name)
                        current_list = cleaned_name
                mode = "normal"
                view = "tasks"
                edit_text = ""
                edit_cursor = 0
                hover = 0
                tasks_scroll = 0
                fuzzy_scroll = 0
                term.clear_screen()
            elif len(key) == 1 and ord(key) >= 32:
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1

        elif mode == "normal":
            if view == "lists_menu":
                if key in ("q", term.KEY_ESC):
                    break
                elif key in (term.KEY_ARROW_UP, "k"):
                    if hover > 0:
                        hover -= 1
                elif key in (term.KEY_ARROW_DOWN, "j"):
                    lists = db.get_all_lists()
                    if hover < len(lists) - 1:
                        hover += 1
                elif key == term.KEY_PAGE_UP:
                    hover = _page_index(
                        hover,
                        len(db.get_all_lists()),
                        max(1, (console.height or 24) - 6),
                        -1,
                    )
                    lists_scroll = hover
                elif key == term.KEY_PAGE_DOWN:
                    hover = _page_index(
                        hover,
                        len(db.get_all_lists()),
                        max(1, (console.height or 24) - 6),
                        1,
                    )
                    lists_scroll = hover
                elif key == term.KEY_ENTER:
                    lists = db.get_all_lists()
                    if lists:
                        current_list = lists[hover]
                    view = "tasks"
                    hover = 0
                    tasks_scroll = 0
                    term.clear_screen()
                elif key == "a":
                    mode = "new_list"
                    edit_text = ""
                    edit_cursor = 0
                elif key == "e":
                    lists = db.get_all_lists()
                    if lists:
                        mode = "edit"
                        edit_text = lists[hover]
                        edit_cursor = len(edit_text)
                elif key == "A":
                    lists = db.get_all_lists()
                    if lists:
                        confirm_list_name = lists[hover]
                        confirm_action = "archive_list"
                        mode = "confirm"
                elif key == ",":
                    term.clear_screen()
                    _run_archived_lists_loop()
                    active_lists = db.get_all_lists()
                    if active_lists and current_list not in active_lists:
                        current_list = active_lists[0]
                    hover = min(hover, max(0, len(active_lists) - 1))
                    term.clear_screen()
                elif key == "d":
                    lists = db.get_all_lists()
                    if lists:
                        confirm_list_name = lists[hover]
                        confirm_action = "delete_list"
                        mode = "confirm"
                elif key in (term.KEY_SHIFT_ARROW_UP, term.KEY_CTRL_ARROW_UP, "K"):
                    lists = db.get_all_lists()
                    if hover > 0:
                        current_lst = lists[hover]
                        db.move_list(current_lst, -1)
                        hover -= 1
                elif key in (term.KEY_SHIFT_ARROW_DOWN, term.KEY_CTRL_ARROW_DOWN, "J"):
                    lists = db.get_all_lists()
                    if hover < len(lists) - 1:
                        current_lst = lists[hover]
                        db.move_list(current_lst, 1)
                        hover += 1
                elif key == "/":
                    lists = db.get_all_lists()
                    active_l = lists[hover] if lists else current_list
                    term.clear_screen()
                    run_settings(active_l)
                    term.clear_screen()
                    continue
                elif key == "?":
                    mode = "help"

            elif view == "tasks":
                if key in ("l", "\t") and not lock_list:
                    view = "lists_menu"
                    lists = db.get_all_lists()
                    if current_list in lists:
                        hover = lists.index(current_list)
                    else:
                        hover = 0
                    term.clear_screen()
                    continue
                elif key in ("q", term.KEY_ESC):
                    break
                # Fuzzy finder trigger
                elif key == term.KEY_CTRL_P and not lock_list:
                    mode = "fuzzy_list"
                    edit_text = ""
                    edit_cursor = 0
                    hover = 0
                    fuzzy_scroll = 0
                    continue
                elif key in (term.KEY_ARROW_UP, "k"):
                    if hover > 0:
                        hover -= 1
                elif key in (term.KEY_ARROW_DOWN, "j"):
                    if tasks and hover < len(tasks) - 1:
                        hover += 1
                elif key == term.KEY_PAGE_UP:
                    hover = _task_page_hover(
                        tasks,
                        hover,
                        min(len(_normal_hint_text(lock_list)), console.width or 80),
                        _task_visible_rows(mode, status_msg, console.height or 24),
                        -1,
                    )
                    starts, _, total_rows = _task_visual_row_ranges(
                        tasks,
                        hover,
                        min(len(_normal_hint_text(lock_list)), console.width or 80),
                    )
                    visible_rows = _task_visible_rows(
                        mode, status_msg, console.height or 24
                    )
                    tasks_scroll = min(
                        starts[hover], max(0, total_rows - visible_rows)
                    ) if tasks else 0
                elif key == term.KEY_PAGE_DOWN:
                    hover = _task_page_hover(
                        tasks,
                        hover,
                        min(len(_normal_hint_text(lock_list)), console.width or 80),
                        _task_visible_rows(mode, status_msg, console.height or 24),
                        1,
                    )
                    starts, _, total_rows = _task_visual_row_ranges(
                        tasks,
                        hover,
                        min(len(_normal_hint_text(lock_list)), console.width or 80),
                    )
                    visible_rows = _task_visible_rows(
                        mode, status_msg, console.height or 24
                    )
                    tasks_scroll = min(
                        starts[hover], max(0, total_rows - visible_rows)
                    ) if tasks else 0
                elif key == term.KEY_ARROW_LEFT and not lock_list:
                    lists = db.get_all_lists()
                    if current_list in lists:
                        curr_idx = lists.index(current_list)
                        next_idx = max(0, curr_idx - 1)
                        current_list = lists[next_idx]
                        hover = 0
                        tasks_scroll = 0
                elif key == term.KEY_ARROW_RIGHT and not lock_list:
                    lists = db.get_all_lists()
                    if current_list in lists:
                        curr_idx = lists.index(current_list)
                        next_idx = min(len(lists) - 1, curr_idx + 1)
                        current_list = lists[next_idx]
                        hover = 0
                        tasks_scroll = 0
                elif key in (term.KEY_SHIFT_ARROW_UP, term.KEY_CTRL_ARROW_UP):
                    if tasks and hover > 0:
                        db.move_task(tasks[hover]["id"], -1)
                        hover -= 1
                elif key in (term.KEY_SHIFT_ARROW_DOWN, term.KEY_CTRL_ARROW_DOWN):
                    if tasks and hover < len(tasks) - 1:
                        db.move_task(tasks[hover]["id"], 1)
                        hover += 1
                elif key == term.KEY_ALT_ARROW_UP:
                    limit = db.get_max_tasks(current_list)
                    if tasks and hover > 0 and len(tasks) < limit:
                        db.duplicate_task(tasks[hover]["id"], -1)
                        tasks = db.get_active_tasks(current_list)
                        hover -= 1
                    elif tasks and len(tasks) >= limit:
                        status_msg = f"max tasks reached ({limit})"
                elif key == term.KEY_ALT_ARROW_DOWN:
                    limit = db.get_max_tasks(current_list)
                    if tasks and len(tasks) < limit:
                        db.duplicate_task(tasks[hover]["id"], 1)
                        tasks = db.get_active_tasks(current_list)
                        hover += 1
                    elif tasks:
                        status_msg = f"max tasks reached ({limit})"
                elif key in (term.KEY_ENTER, "e"):
                    if tasks:
                        if tasks[hover].get("is_note"):
                            _run_note_editor(tasks[hover]["note_id"])
                            term.clear_screen()
                        else:
                            mode = "edit"
                            edit_task_id = tasks[hover]["id"]
                            edit_text = tasks[hover]["text"]
                            edit_cursor = len(edit_text)
                elif key == "E":
                    if tasks and tasks[hover].get("is_note"):
                        mode = "edit"
                        edit_note_id = tasks[hover]["note_id"]
                        edit_text = tasks[hover]["text"]
                        edit_cursor = len(edit_text)
                elif key == "a":
                    limit = db.get_max_tasks(current_list)
                    if len(tasks) < limit:
                        new_task = db.add_task("", current_list)
                        if new_task:
                            tasks = db.get_active_tasks(current_list)
                            hover = len(tasks) - 1
                            edit_task_id = new_task["id"]
                            edit_text = ""
                            edit_cursor = 0
                            mode = "edit"
                    else:
                        status_msg = f"max tasks reached ({limit})"
                elif key == "A":
                    limit = db.get_max_tasks(current_list)
                    if len(tasks) < limit:
                        edit_text = _default_note_title()
                        edit_cursor = len(edit_text)
                        mode = "new_note"
                    else:
                        status_msg = f"max items reached ({limit})"
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
                elif key == "s":
                    if tasks:
                        db.toggle_starred(tasks[hover]["id"])
                elif key == "y":
                    # Yank copy
                    active_tasks = db.get_active_tasks(current_list)
                    if active_tasks:
                        lines = []
                        for t in active_tasks:
                            marker = "★" if t.get("starred", 0) == 1 else "○"
                            lines.append(f"{marker} {t['text']}")
                        content = "\n".join(lines)
                        _copy_to_clipboard(content)
                elif key == ",":
                    term.clear_screen()
                    run_archive(current_list, lock_list)
                    term.clear_screen()
                    continue
                elif key == "/":
                    term.clear_screen()
                    run_settings(current_list)
                    term.clear_screen()
                    continue
                elif key == "?":
                    mode = "help"

        elif mode == "confirm":
            if key in ("y", term.KEY_ENTER):
                if confirm_action == "delete" and confirm_task_id is not None:
                    db.delete_task(confirm_task_id)
                    tasks = db.get_active_tasks(current_list)
                    if hover >= len(tasks) and hover > 0:
                        hover = len(tasks) - 1
                elif confirm_action == "archive":
                    db.archive_done(current_list)
                elif confirm_action == "delete_list":
                    db.delete_list(confirm_list_name)
                    lists = db.get_all_lists()
                    if current_list == confirm_list_name:
                        current_list = lists[0] if lists else "main"
                    hover = 0
                    view = "lists_menu"
                elif confirm_action == "archive_list":
                    db.archive_list(confirm_list_name)
                    lists = db.get_all_lists()
                    if current_list == confirm_list_name:
                        current_list = lists[0] if lists else "main"
                    hover = min(hover, max(0, len(lists) - 1))
                    view = "lists_menu"
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None
                confirm_list_name = ""
            else:
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None
                confirm_list_name = ""

        elif mode == "edit":
            if key == term.KEY_ESC:
                if view == "tasks" and edit_task_id:
                    current = next((t for t in db.get_active_tasks(current_list) if t["id"] == edit_task_id), None)
                    if current and not current["text"]:
                        db.delete_task(edit_task_id)
                mode = "normal"
                edit_task_id = None
                edit_note_id = None
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                if view == "tasks" and edit_note_id:
                    db.update_note_title(edit_note_id, edit_text)
                elif view == "tasks" and edit_task_id:
                    db.update_task_text(edit_task_id, edit_text)
                elif view == "lists_menu":
                    lists = db.get_all_lists()
                    if lists:
                        old_name = lists[hover]
                        if db.rename_list(old_name, edit_text):
                            if current_list == old_name:
                                current_list = edit_text.strip()
                mode = "normal"
                edit_task_id = None
                edit_note_id = None
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
                edit_cursor = max(0, edit_cursor - 1)
            elif key == term.KEY_ARROW_RIGHT:
                edit_cursor = min(len(edit_text), edit_cursor + 1)
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif key in (term.KEY_ARROW_UP, term.KEY_ARROW_DOWN):
                pass
            elif len(key) == 1 and ord(key) >= 32:
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1

        elif mode == "new_note":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                new_note = db.add_note(edit_text, current_list)
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
                if new_note:
                    tasks = db.get_active_tasks(current_list)
                    hover = next(
                        (i for i, task in enumerate(tasks) if task.get("note_id") == new_note["id"]),
                        max(0, len(tasks) - 1),
                    )
                    _run_note_editor(new_note["id"])
                    term.clear_screen()
            elif key == term.KEY_BACKSPACE:
                if edit_cursor > 0:
                    edit_text = edit_text[:edit_cursor - 1] + edit_text[edit_cursor:]
                    edit_cursor -= 1
            elif key == term.KEY_DELETE:
                if edit_cursor < len(edit_text):
                    edit_text = edit_text[:edit_cursor] + edit_text[edit_cursor + 1:]
            elif key == term.KEY_ARROW_LEFT:
                edit_cursor = max(0, edit_cursor - 1)
            elif key == term.KEY_ARROW_RIGHT:
                edit_cursor = min(len(edit_text), edit_cursor + 1)
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif len(key) == 1 and ord(key) >= 32:
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1

        elif mode == "new_list":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                cleaned_name = edit_text.strip()
                if cleaned_name:
                    db.create_list(cleaned_name)
                    current_list = cleaned_name
                    hover = 0
                    view = "tasks"
                    tasks_scroll = 0
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
                edit_cursor = max(0, edit_cursor - 1)
            elif key == term.KEY_ARROW_RIGHT:
                edit_cursor = min(len(edit_text), edit_cursor + 1)
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif len(key) == 1 and ord(key) >= 32:
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1


def _run_archive_loop(list_name: str = "main", lock_list: bool = False) -> None:
    hover = 0
    scroll = 0
    term_height = console.height or 24
    mode = "normal"
    confirm_action: str = ""  # "delete", "archive", "clear"
    confirm_task_id: int | None = None

    while True:
        term_height = console.height or 24
        tasks = db.get_archived_tasks(list_name)
        if not tasks:
            hover = 0
            scroll = 0
        else:
            if hover >= len(tasks):
                hover = len(tasks) - 1
            # Auto-scroll to keep hover visible
            max_lines = max(1, term_height - 6 - (2 if mode == "confirm" else 0))
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

        _render_archive(tasks, hover, scroll, term_height, mode, confirm_msg, list_name)

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
            elif key == term.KEY_PAGE_UP:
                hover = _page_index(
                    hover, len(tasks), max(1, term_height - 6), -1
                )
                scroll = hover
            elif key == term.KEY_PAGE_DOWN:
                hover = _page_index(
                    hover, len(tasks), max(1, term_height - 6), 1
                )
                scroll = hover
            elif key == "d":
                if tasks:
                    confirm_action = "delete"
                    confirm_task_id = tasks[hover]["id"]
                    mode = "confirm"
            elif key == "r":
                if tasks:
                    restored = db.restore_task(tasks[hover]["id"])
                    if restored:
                        tasks = db.get_archived_tasks(list_name)
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
                    tasks = db.get_archived_tasks(list_name)
                    if hover >= len(tasks) and hover > 0:
                        hover = len(tasks) - 1
                elif confirm_action == "clear":
                    db.clear_archived(list_name)
                    hover = 0
                    scroll = 0
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None
            else:
                mode = "normal"
                confirm_action = ""
                confirm_task_id = None


@_buffered_frame
def _render_settings(
    list_name: str,
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    edit_cursor: int = 0,
    status_msg: str = "",
) -> None:
    max_tasks = db.get_max_tasks(list_name)
    max_starred = db.get_max_starred_tasks()

    header = Text("settings • ", style="bold")
    header.append(Text(f"preferences ({list_name})", style="dim"))
    console.print(header, end="\033[K\n")

    if mode == "edit":
        if hover in (0, 1):
            hint_text = "  " + " │ ".join(["Esc:cancel", "Enter:confirm", "↑/↓:adjust value"])
        else:
            hint_text = "  " + " │ ".join(["Esc:cancel", "Enter:confirm"])
    else:
        hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "PgUp/PgDn:page", "e:edit", "Enter:select", "q:return"])

    divider_width = min(len(_normal_hint_text(False)), console.width or 80)
    console.print(Text("─" * divider_width, style="dim"), end="\033[K\n")
    console.print(end="\033[K\n")

    # Max tasks row
    is_hovered_max = hover == 0
    prefix = "▸ " if is_hovered_max else "  "
    max_line = Text(prefix)
    if mode == "edit" and hover == 0:
        max_line = Text(prefix)
        max_line.append(Text(f"max tasks ({list_name}): ", style="cyan bold"))
        max_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        max_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            max_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
    elif is_hovered_max:
        max_line.append(Text(f"max tasks ({list_name}): ", style="cyan bold"))
        max_line.append(Text(str(max_tasks), style="bold"))
    else:
        max_line.append(Text(f"max tasks ({list_name}): ", style="dim"))
        max_line.append(Text(str(max_tasks), style="dim"))
    console.print(max_line, end="\033[K\n")

    # Max starred tasks row
    is_hovered_starred = hover == 1
    prefix_starred = "▸ " if is_hovered_starred else "  "
    starred_line = Text(prefix_starred)
    if mode == "edit" and hover == 1:
        starred_line = Text(prefix_starred)
        starred_line.append(Text("max starred tasks: ", style="cyan bold"))
        starred_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        starred_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            starred_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
    elif is_hovered_starred:
        starred_line.append(Text("max starred tasks: ", style="cyan bold"))
        starred_line.append(Text(str(max_starred), style="bold"))
    else:
        starred_line.append(Text("max starred tasks: ", style="dim"))
        starred_line.append(Text(str(max_starred), style="dim"))
    console.print(starred_line, end="\033[K\n")

    # Database encryption row
    is_hovered_enc = hover == 2
    prefix_enc = "▸ " if is_hovered_enc else "  "
    enc_line = Text(prefix_enc)
    enc_status = "enabled" if db.is_encryption_enabled() else "disabled"
    if is_hovered_enc:
        enc_line.append(Text("database encryption: ", style="cyan bold"))
        enc_line.append(Text(enc_status, style="bold"))
    else:
        enc_line.append(Text("database encryption: ", style="dim"))
        enc_line.append(Text(enc_status, style="dim"))
    console.print(enc_line, end="\033[K\n")

    # Current-list encryption row
    is_hovered_list_enc = hover == 3
    prefix_list_enc = "▸ " if is_hovered_list_enc else "  "
    list_enc_line = Text(prefix_list_enc)
    if db.is_list_encryption_enabled(list_name):
        list_enc_status = "unlocked" if db.is_list_unlocked(list_name) else "locked"
    else:
        list_enc_status = "disabled"
    if is_hovered_list_enc:
        list_enc_line.append(Text(f"list encryption ({list_name}): ", style="cyan bold"))
        list_enc_line.append(Text(list_enc_status, style="bold"))
    else:
        list_enc_line.append(Text(f"list encryption ({list_name}): ", style="dim"))
        list_enc_line.append(Text(list_enc_status, style="dim"))
    console.print(list_enc_line, end="\033[K\n")

    # Update row
    is_hovered_update = hover == 4
    prefix2 = "▸ " if is_hovered_update else "  "
    update_line = Text(prefix2)
    if is_hovered_update:
        update_line.append(Text("update td", style="cyan bold"))
    else:
        update_line.append(Text("update td", style="dim"))
    console.print(update_line, end="\033[K\n")

    # Export row
    is_hovered_export = hover == 5
    prefix_exp = "▸ " if is_hovered_export else "  "
    export_line = Text(prefix_exp)
    if mode == "edit" and hover == 5:
        export_line.append(Text("export database: ", style="cyan bold"))
        export_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        export_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            export_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
    elif is_hovered_export:
        export_line.append(Text("export database", style="cyan bold"))
    else:
        export_line.append(Text("export database", style="dim"))
    console.print(export_line, end="\033[K\n")

    # Import row
    is_hovered_import = hover == 6
    prefix_imp = "▸ " if is_hovered_import else "  "
    import_line = Text(prefix_imp)
    if mode == "edit" and hover == 6:
        import_line.append(Text("import database: ", style="cyan bold"))
        import_line.append(Text(edit_text[:edit_cursor], style="yellow bold"))
        char_under = edit_text[edit_cursor] if edit_cursor < len(edit_text) else " "
        import_line.append(Text(char_under, style="reverse yellow bold"))
        if edit_cursor < len(edit_text):
            import_line.append(Text(edit_text[edit_cursor + 1:], style="yellow bold"))
    elif is_hovered_import:
        import_line.append(Text("import database", style="cyan bold"))
    else:
        import_line.append(Text("import database", style="dim"))
    console.print(import_line, end="\033[K\n")

    if status_msg:
        console.print(end="\033[K\n")
        console.print(Text(f"  {status_msg}", style="yellow bold"), end="\033[K\n")

    console.print(end="\033[K\n")
    console.print(Text("─" * divider_width, style="dim"), end="\033[K\n")
    console.print(
        _footer_with_version(hint_text, divider_width),
        end="\033[K\n",
        overflow="crop",
        no_wrap=True,
    )


def _run_settings_loop(list_name: str) -> None:
    hover = 0
    mode = "normal"
    edit_text = ""
    edit_cursor = 0
    status_msg = ""
    num_items = 7

    while True:
        _render_settings(list_name, hover, mode, edit_text, edit_cursor, status_msg)
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
            elif key == term.KEY_PAGE_UP:
                hover = _page_index(
                    hover, num_items, max(1, (console.height or 24) - 6), -1
                )
            elif key == term.KEY_PAGE_DOWN:
                hover = _page_index(
                    hover, num_items, max(1, (console.height or 24) - 6), 1
                )
            elif key in (term.KEY_ENTER, "e"):
                if hover == 0:
                    mode = "edit"
                    edit_text = str(db.get_max_tasks(list_name))
                    edit_cursor = len(edit_text)
                elif hover == 1:
                    mode = "edit"
                    edit_text = str(db.get_max_starred_tasks())
                    edit_cursor = len(edit_text)
                elif hover == 5:
                    mode = "edit"
                    edit_text = "backup.json"
                    edit_cursor = len(edit_text)
                elif hover == 6:
                    mode = "edit"
                    edit_text = "backup.json"
                    edit_cursor = len(edit_text)
                elif hover == 2:
                    # Toggle encryption
                    if not db.is_encryption_enabled() and db.get_encrypted_lists():
                        status_msg = "✗ disable list encryption first"
                    elif not db.is_encryption_enabled():
                        # Prompt warning
                        term.clear_screen()
                        console.print()
                        console.print(Text("  [!] WARNING: If you forget your password, your tasks will be", style="yellow bold"))
                        console.print(Text("      permanently lost. There is no password recovery option.", style="yellow bold"))
                        console.print()
                        console.print(Text("  Press Enter to continue, or Esc to cancel...", style="dim"))

                        confirm_key = ""
                        while confirm_key not in (term.KEY_ENTER, "\r", "\n", term.KEY_ESC):
                            confirm_key = term.read_key()

                        if confirm_key in (term.KEY_ENTER, "\r", "\n"):
                            password = prompt_password("Create password to encrypt database: ")
                            if password:
                                confirm = prompt_password("Confirm password: ")
                                if password == confirm:
                                    try:
                                        db.enable_encryption(password)
                                        status_msg = "✓ database encrypted successfully"
                                    except ValueError as error:
                                        status_msg = f"✗ {error}"
                                else:
                                    status_msg = "✗ passwords do not match"
                            else:
                                status_msg = "✗ password cannot be empty"
                        else:
                            status_msg = "  cancelled"
                    else:
                        password = prompt_password("Enter password to disable encryption: ")
                        if password:
                            if db.disable_encryption(password):
                                status_msg = "✓ encryption disabled successfully"
                            else:
                                status_msg = "✗ incorrect password"
                elif hover == 3:
                    if db.is_encryption_enabled():
                        status_msg = "✗ disable database encryption first"
                    elif not db.is_list_encryption_enabled(list_name):
                        term.clear_screen()
                        console.print()
                        console.print(Text(
                            f'  Encrypt list "{list_name}" and all its tasks and notes?',
                            style="yellow bold",
                        ))
                        console.print(Text(
                            "  Forgotten passwords cannot be recovered.", style="yellow bold"
                        ))
                        console.print()
                        console.print(Text("  Press Enter to continue, or Esc to cancel...", style="dim"))
                        confirm_key = ""
                        while confirm_key not in (term.KEY_ENTER, "\r", "\n", term.KEY_ESC):
                            confirm_key = term.read_key()
                        if confirm_key in (term.KEY_ENTER, "\r", "\n"):
                            password = prompt_password(f'Create password for list "{list_name}": ')
                            confirm = prompt_password("Confirm password: ") if password else ""
                            if not password:
                                status_msg = "✗ password cannot be empty"
                            elif password != confirm:
                                status_msg = "✗ passwords do not match"
                            else:
                                try:
                                    db.enable_list_encryption(list_name, password)
                                    status_msg = f'✓ list "{list_name}" encrypted'
                                except ValueError as error:
                                    status_msg = f"✗ {error}"
                        else:
                            status_msg = "cancelled"
                    else:
                        password = prompt_password(f'Enter password to decrypt list "{list_name}": ')
                        if password and db.disable_list_encryption(list_name, password):
                            status_msg = f'✓ list "{list_name}" encryption disabled'
                        else:
                            status_msg = "✗ incorrect password"
                elif hover == 4:
                    # Run update
                    import subprocess
                    result = subprocess.run(
                        ["uv", "tool", "upgrade", "td-task"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if result.returncode == 0:
                        output = (result.stdout + result.stderr).strip()
                        if "Nothing to upgrade" in output:
                            status_msg = "already up-to-date."
                        else:
                            status_msg = "✓ updated successfully"
                            term.clear_screen()
                            console.print(Text("✓ td updated successfully!", style="green bold"))
                            console.print()
                            import os
                            from rich.markdown import Markdown
                            changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
                            if os.path.exists(changelog_path):
                                try:
                                    with open(changelog_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                    console.print(Markdown(content))
                                except Exception:
                                    pass
                            console.print()
                            console.print(Text("Press any key to return to settings...", style="dim"))
                            term.read_key()
                    else:
                        status_msg = f"✗ update failed: {result.stderr.strip().split(chr(10))[-1]}"

        elif mode == "edit":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                if hover == 0:
                    try:
                        new_max = int(edit_text)
                        if new_max < 3 or new_max > 50:
                            raise ValueError
                        db.set_max_tasks(new_max, list_name)
                        status_msg = f"✓ max tasks set to {new_max} for list '{list_name}'"
                    except ValueError:
                        status_msg = "✗ must be an integer between 3 and 50"
                elif hover == 1:
                    try:
                        new_max = int(edit_text)
                        cap = max(20, db.get_max_tasks(list_name))
                        if new_max < 1 or new_max > cap:
                            raise ValueError
                        db.set_max_starred_tasks(new_max)
                        status_msg = f"✓ max starred tasks set to {new_max}"
                    except ValueError:
                        cap = max(20, db.get_max_tasks(list_name))
                        status_msg = f"✗ must be an integer between 1 and {cap}"
                elif hover == 5:
                    try:
                        filename = edit_text.strip()
                        if not filename:
                            raise ValueError("Filename cannot be empty")
                        json_data = db.export_to_json()
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(json_data)
                        status_msg = f"✓ database exported to {filename}"
                    except Exception as e:
                        status_msg = f"✗ export failed: {e}"
                elif hover == 6:
                    try:
                        filename = edit_text.strip()
                        if not filename:
                            raise ValueError("Filename cannot be empty")
                        if not os.path.exists(filename):
                            raise FileNotFoundError(f"'{filename}' not found")
                        with open(filename, "r", encoding="utf-8") as f:
                            json_str = f.read()
                        db.import_from_json(json_str)
                        status_msg = f"✓ database imported from {filename}"
                    except Exception as e:
                        status_msg = f"✗ import failed: {e}"
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
            elif hover == 0 and key == term.KEY_ARROW_UP:
                try:
                    val = int(edit_text) if edit_text.strip() else 3
                except ValueError:
                    val = 3
                new_val = min(50, val + 1)
                edit_text = str(new_val)
                edit_cursor = len(edit_text)
            elif hover == 0 and key == term.KEY_ARROW_DOWN:
                try:
                    val = int(edit_text) if edit_text.strip() else 3
                except ValueError:
                    val = 3
                new_val = max(3, val - 1)
                edit_text = str(new_val)
                edit_cursor = len(edit_text)
            elif hover == 1 and key == term.KEY_ARROW_UP:
                try:
                    val = int(edit_text) if edit_text.strip() else 1
                except ValueError:
                    val = 1
                cap = max(20, db.get_max_tasks(list_name))
                new_val = min(cap, val + 1)
                edit_text = str(new_val)
                edit_cursor = len(edit_text)
            elif hover == 1 and key == term.KEY_ARROW_DOWN:
                try:
                    val = int(edit_text) if edit_text.strip() else 1
                except ValueError:
                    val = 1
                new_val = max(1, val - 1)
                edit_text = str(new_val)
                edit_cursor = len(edit_text)
            elif key == term.KEY_BACKSPACE:
                if edit_cursor > 0:
                    edit_text = edit_text[:edit_cursor - 1] + edit_text[edit_cursor:]
                    edit_cursor -= 1
            elif key == term.KEY_DELETE:
                if edit_cursor < len(edit_text):
                    edit_text = edit_text[:edit_cursor] + edit_text[edit_cursor + 1:]
            elif key == term.KEY_ARROW_LEFT:
                edit_cursor = max(0, edit_cursor - 1)
            elif key == term.KEY_ARROW_RIGHT:
                edit_cursor = min(len(edit_text), edit_cursor + 1)
            elif key == term.KEY_HOME:
                edit_cursor = 0
            elif key == term.KEY_END:
                edit_cursor = len(edit_text)
            elif len(key) == 1 and (key.isdigit() or (hover in (5, 6) and ord(key) >= 32)):
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1


def run_settings(list_name: str = "main") -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            if not _ensure_unlocked():
                return
            if not _ensure_list_unlocked(list_name):
                return
            _run_settings_loop(list_name)
        except KeyboardInterrupt:
            pass
        finally:
            term.show_cursor()


def run_main(list_name: str = "main", lock_list: bool = False) -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            if not _ensure_unlocked():
                return
            _run_main_loop(list_name, lock_list)
        except KeyboardInterrupt:
            pass
        finally:
            term.show_cursor()
            term.clear_screen()


def run_archive(list_name: str = "main", lock_list: bool = False) -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            if not _ensure_unlocked():
                return
            if not _ensure_list_unlocked(list_name):
                return
            _run_archive_loop(list_name, lock_list)
        except KeyboardInterrupt:
            pass
        finally:
            term.show_cursor()
            term.clear_screen()
