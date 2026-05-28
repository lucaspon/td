from __future__ import annotations

import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text

from . import db
from . import terminal as term

console = Console()


def _copy_to_clipboard(text: str) -> bool:
    import subprocess
    try:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"))
        return p.returncode == 0
    except Exception:
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


def _normal_hint_text(lock_list: bool = False) -> str:
    parts = ["a:add", "e:edit", "d:delete", "Space:done", "s:star", "c:clear"]
    if not lock_list:
        parts.append("l:view lists")
    parts.append("q:quit")
    parts.append("?:help")
    return "  " + " │ ".join(parts)


def _render_help_screen(lock_list: bool = False) -> None:
    term.reset_cursor()

    header = Text("help • ", style="bold")
    header.append(Text("keybindings & commands", style="dim"))
    console.print(header)
    
    # Calculate divider width dynamically
    divider_width = min(len(_normal_hint_text(lock_list)), console.width or 80)
    console.print(Text("─" * divider_width, style="dim"))
    console.print()

    # Group 1: Task Actions
    console.print(Text("Task Actions:", style="bold yellow"))
    console.print("  a           Add a new task")
    console.print("  e / Enter   Edit selected task")
    console.print("  d           Delete selected task")
    console.print("  Space       Toggle task done/active")
    console.print("  s           Toggle star/priority (pin to top)")
    console.print("  c           Archive all completed tasks")
    console.print("  y           Copy active tasks in list to clipboard")
    console.print()

    # Group 2: Lists & Navigation
    console.print(Text("Lists & Navigation:", style="bold yellow"))
    console.print("  ↑/k  ↓/j    Navigate tasks / lists")
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
    console.print(Text("  Press any key to return...", style="dim"))
    sys.stdout.write("\033[J")
    sys.stdout.flush()


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
) -> None:
    term.reset_cursor()

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
    elif mode == "confirm":
        hint_parts = ["Enter:confirm", "Esc:cancel"]
    elif mode == "fuzzy_list":
        hint_parts = ["Esc:cancel", "Enter:go to list", "↑/↓:navigate matches"]
    else:
        # mode == "normal"
        if view == "lists_menu":
            hint_parts = ["a:add", "e:edit", "d:delete", "Enter:open", "q:quit"]
        else:
            hint_parts = ["a:add", "e:edit", "d:delete", "Space:done", "s:star", "c:clear"]
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
        else:
            for idx, match_item in enumerate(matched):
                is_selected = idx == hover
                prefix = "  ▸ " if is_selected else "    "
                if is_selected:
                    console.print(Text(f"{prefix}{match_item}", style="bold cyan"), end="\033[K\n")
                else:
                    console.print(Text(f"{prefix}{match_item}", style="dim"), end="\033[K\n")
    elif view == "lists_menu":
        lists = db.get_all_lists()
        lines = []
        for i, lst in enumerate(lists):
            is_hovered = i == hover
            prefix = "▸ " if is_hovered else "  "
            
            if mode == "edit" and is_hovered:
                # inline list editing
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
                if is_hovered:
                    lines.append(Text(f"▸ {lst}", style="bold cyan"))
                else:
                    lines.append(Text(f"  {lst}"))
                    
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
            
        for line in lines:
            console.print(line, end="\033[K\n")
    else:
        lines = []
        prev_starred = False
        for i, task in enumerate(tasks):
            is_hovered = i == hover
            is_done = task["status"] == "done"
            is_starred = task.get("starred", 0) == 1

            if i > 0 and prev_starred and not is_starred:
                lines.append(Text(""))

            prefix = "▸ " if is_hovered else "  "
            marker = "★" if is_starred else ("✓" if is_done else "○")

            if mode == "edit" and i == hover:
                edit_style = "bold yellow" if is_starred else "cyan bold"
                cursor_style = "reverse bold yellow" if is_starred else "reverse cyan bold"
                
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
                    line_text = Text(text, style="strike dim")
                elif is_hovered:
                    if is_starred:
                        line_text = Text(text, style="bold yellow")
                    else:
                        line_text = Text(text, style="cyan bold")
                else:
                    if is_starred:
                        line_text = Text(text, style="bold yellow")
                    else:
                        line_text = Text(text)

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
                            w_text_obj.style = "strike dim"
                        elif is_hovered:
                            w_text_obj.style = "bold yellow" if is_starred else "cyan bold"
                        elif is_starred:
                            w_text_obj.style = "bold yellow"
                        
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
            lines.append(Text("  No tasks. Press a to add one.", style="dim"))

        for line in lines:
            console.print(line, end="\033[K\n")

    if mode == "confirm":
        console.print(end="\033[K\n")
        console.print(Text(f"  {confirm_msg}", style="yellow bold"), end="\033[K\n")

    console.print(end="\033[K\n")
    console.print(Text("─" * divider_width, style="dim"), end="\033[K\n")
    console.print(Text(hint_text, style="dim"), end="\033[K\n")
    sys.stdout.write("\033[J")
    sys.stdout.flush()


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
    list_name: str = "main",
) -> None:
    term.reset_cursor()

    header = Text(f"archive • {list_name} • ", style="bold")
    header.append(Text(f"{len(tasks)} tasks", style="dim"))
    console.print(header)

    if mode == "confirm":
        hint_text = "  " + " │ ".join(["Enter:confirm", "Esc:cancel"])
    else:
        hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "d:delete", "r:restore", "c:clear", "q:return"])

    divider_width = min(len(_normal_hint_text()), console.width or 80)
    console.print(Text("─" * divider_width, style="dim"))
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

    console.print()
    console.print(Text("─" * divider_width, style="dim"))
    console.print(Text(hint_text, style="dim"))
    sys.stdout.write("\033[J")
    sys.stdout.flush()


def _run_main_loop(list_name: str = "main", lock_list: bool = False) -> None:
    hover = 0
    mode = "normal"
    view = "tasks"  # can be "tasks" or "lists_menu"
    edit_task_id: int | None = None
    edit_text = ""
    edit_cursor = 0
    confirm_action: str = ""  # "delete", "archive", "delete_list"
    confirm_task_id: int | None = None
    confirm_list_name = ""

    current_list = list_name

    while True:
        if mode == "help":
            term.clear_screen()
            _render_help_screen(lock_list)
            term.read_key()
            term.clear_screen()
            mode = "normal"
            continue

        tasks = db.get_active_tasks(current_list)
        
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
        elif view == "lists_menu":
            lists = db.get_all_lists()
            if lists and hover >= len(lists):
                hover = len(lists) - 1
            if not lists:
                hover = 0
        else:
            if tasks and hover >= len(tasks):
                hover = len(tasks) - 1
            if not tasks:
                hover = 0

        # Construct confirmation message
        if mode == "confirm" and confirm_action == "archive":
            confirm_msg = "Clear all done tasks?"
        elif mode == "confirm" and confirm_action == "delete":
            task_text = next((t["text"] for t in tasks if t["id"] == confirm_task_id), "")
            confirm_msg = f'Delete "{task_text}"?'
        elif mode == "confirm" and confirm_action == "delete_list":
            confirm_msg = f'Delete list "{confirm_list_name}"? All tasks inside will be permanently lost!'
        else:
            confirm_msg = ""

        _render_main(tasks, hover, mode, edit_text, edit_cursor, confirm_msg, current_list, lock_list, view)

        key = term.read_key()

        # Fuzzy list mode logic
        if mode == "fuzzy_list":
            if key == term.KEY_ESC:
                mode = "normal"
                edit_text = ""
                edit_cursor = 0
                hover = 0
            elif key == term.KEY_ARROW_UP:
                if hover > 0:
                    hover -= 1
            elif key == term.KEY_ARROW_DOWN:
                if matched and hover < len(matched) - 1:
                    hover += 1
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
                elif key == term.KEY_ENTER:
                    lists = db.get_all_lists()
                    if lists:
                        current_list = lists[hover]
                    view = "tasks"
                    hover = 0
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
                    continue
                elif key in (term.KEY_ARROW_UP, "k"):
                    if hover > 0:
                        hover -= 1
                elif key in (term.KEY_ARROW_DOWN, "j"):
                    if tasks and hover < len(tasks) - 1:
                        hover += 1
                elif key == term.KEY_ARROW_LEFT and not lock_list:
                    lists = db.get_all_lists()
                    if current_list in lists:
                        curr_idx = lists.index(current_list)
                        next_idx = max(0, curr_idx - 1)
                        current_list = lists[next_idx]
                        hover = 0
                elif key == term.KEY_ARROW_RIGHT and not lock_list:
                    lists = db.get_all_lists()
                    if current_list in lists:
                        curr_idx = lists.index(current_list)
                        next_idx = min(len(lists) - 1, curr_idx + 1)
                        current_list = lists[next_idx]
                        hover = 0
                elif key in (term.KEY_SHIFT_ARROW_UP, term.KEY_CTRL_ARROW_UP):
                    if tasks and hover > 0:
                        db.move_task(tasks[hover]["id"], -1)
                        hover -= 1
                elif key in (term.KEY_SHIFT_ARROW_DOWN, term.KEY_CTRL_ARROW_DOWN):
                    if tasks and hover < len(tasks) - 1:
                        db.move_task(tasks[hover]["id"], 1)
                        hover += 1
                elif key == term.KEY_ALT_ARROW_UP:
                    if tasks and hover > 0:
                        db.duplicate_task(tasks[hover]["id"], -1)
                        tasks = db.get_active_tasks(current_list)
                        hover -= 1
                elif key == term.KEY_ALT_ARROW_DOWN:
                    if tasks and len(tasks) < db.get_max_tasks():
                        db.duplicate_task(tasks[hover]["id"], 1)
                        tasks = db.get_active_tasks(current_list)
                        hover += 1
                elif key in (term.KEY_ENTER, "e"):
                    if tasks:
                        mode = "edit"
                        edit_task_id = tasks[hover]["id"]
                        edit_text = tasks[hover]["text"]
                        edit_cursor = len(edit_text)
                elif key == "a":
                    if len(tasks) < db.get_max_tasks():
                        new_task = db.add_task("", current_list)
                        if new_task:
                            tasks = db.get_active_tasks(current_list)
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
                edit_text = ""
                edit_cursor = 0
            elif key == term.KEY_ENTER:
                if view == "tasks" and edit_task_id:
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
        tasks = db.get_archived_tasks(list_name)
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


def _render_settings(
    list_name: str,
    hover: int,
    mode: str = "normal",
    edit_text: str = "",
    edit_cursor: int = 0,
    status_msg: str = "",
) -> None:
    term.reset_cursor()

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
        hint_text = "  " + " │ ".join(["↑/k ↓/j:navigate", "e:edit", "Enter:select", "q:return"])

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

    # Encryption row
    is_hovered_enc = hover == 2
    prefix_enc = "▸ " if is_hovered_enc else "  "
    enc_line = Text(prefix_enc)
    enc_status = "enabled" if db.is_encryption_enabled() else "disabled"
    if is_hovered_enc:
        enc_line.append(Text("encryption: ", style="cyan bold"))
        enc_line.append(Text(enc_status, style="bold"))
    else:
        enc_line.append(Text("encryption: ", style="dim"))
        enc_line.append(Text(enc_status, style="dim"))
    console.print(enc_line, end="\033[K\n")

    # Update row
    is_hovered_update = hover == 3
    prefix2 = "▸ " if is_hovered_update else "  "
    update_line = Text(prefix2)
    if is_hovered_update:
        update_line.append(Text("update td", style="cyan bold"))
    else:
        update_line.append(Text("update td", style="dim"))
    console.print(update_line, end="\033[K\n")

    # Export row
    is_hovered_export = hover == 4
    prefix_exp = "▸ " if is_hovered_export else "  "
    export_line = Text(prefix_exp)
    if mode == "edit" and hover == 4:
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
    is_hovered_import = hover == 5
    prefix_imp = "▸ " if is_hovered_import else "  "
    import_line = Text(prefix_imp)
    if mode == "edit" and hover == 5:
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
    console.print(Text(hint_text, style="dim"), end="\033[K\n")
    sys.stdout.write("\033[J")
    sys.stdout.flush()
    sys.stdout.flush()


def _run_settings_loop(list_name: str) -> None:
    hover = 0
    mode = "normal"
    edit_text = ""
    edit_cursor = 0
    status_msg = ""
    num_items = 6  # max_tasks, max_starred_tasks, encryption, update, export, import

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
            elif key in (term.KEY_ENTER, "e"):
                if hover == 0:
                    mode = "edit"
                    edit_text = str(db.get_max_tasks(list_name))
                    edit_cursor = len(edit_text)
                elif hover == 1:
                    mode = "edit"
                    edit_text = str(db.get_max_starred_tasks())
                    edit_cursor = len(edit_text)
                elif hover == 4:
                    mode = "edit"
                    edit_text = "backup.json"
                    edit_cursor = len(edit_text)
                elif hover == 5:
                    mode = "edit"
                    edit_text = "backup.json"
                    edit_cursor = len(edit_text)
                elif hover == 2:
                    # Toggle encryption
                    if not db.is_encryption_enabled():
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
                                    db.enable_encryption(password)
                                    status_msg = "✓ database encrypted successfully"
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
                elif hover == 4:
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
                elif hover == 5:
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
            elif len(key) == 1 and (key.isdigit() or (hover in (4, 5) and ord(key) >= 32)):
                edit_text = edit_text[:edit_cursor] + key + edit_text[edit_cursor:]
                edit_cursor += 1


def run_settings(list_name: str = "main") -> None:
    term.hide_cursor()
    with term.raw_mode():
        try:
            if not _ensure_unlocked():
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
            _run_archive_loop(list_name, lock_list)
        except KeyboardInterrupt:
            pass
        finally:
            term.show_cursor()
            term.clear_screen()