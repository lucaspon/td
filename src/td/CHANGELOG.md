# Changelog

## [0.2.1] - 2026-08-04
- Soft-wrap long note lines to terminal width without changing stored Markdown.
- Keep Markdown preview styling across wrapped rows and scroll with the active cursor.

## [0.2.0] - 2026-08-03
- Add task-backed Markdown notes with a full-screen editor and live line preview.
- Add `A` to create notes, `e`/`Enter` to edit note bodies, and `E` to rename notes.
- Include notes in encryption, JSON backup and restore, list ordering, and task lifecycle actions.
- Add line movement, line clearing, word navigation, word deletion, and indentation controls to the note editor.
- Add restorable list archiving with preserved tasks, notes, settings, and JSON backup state.
- Auto-indent and continue Markdown bullets; exit empty continuation with Enter or Backspace.
- Add independent password encryption per list with portable encrypted backups and lazy unlock prompts.
- Add agent-friendly notes CLI with CRUD actions, JSON output, and file or stdin bodies.

## [0.1.5]
- Fix Windows keyboard input: arrow keys, Home/End, Delete, and Ctrl/Alt+arrow now work by decoding the native Windows scancode protocol instead of assuming ANSI escape sequences.
- Fix clipboard copy (`y`) on Windows by using the `clip` command.
- Gracefully degrade if a console cannot enable virtual terminal mode, instead of crashing on startup.

## [0.1.4]
- Fix list-scoped max tasks limit not being respected when adding or duplicating tasks in the TUI.


## [0.1.3]
- Add vertical Lists Menu screen to view and manage lists vertically with smooth screen transitions.
- Support inline list creation, list renaming, deletion, and position reordering in the Lists Menu view.
- Add list-scoped max tasks limits that can be edited in settings.
- Polish task editing colors: preserve yellow for starred tasks and bold cyan/blue for normal tasks.
- Add JSON database backup export and import utilities directly in the TUI preference settings menu.
- Enforce explicit list name validation on CLI commands (`list`, `add`, `archive`) via `-l` / `--list`.
- Default to "main" list on clean installation / first usage.
- Add "l:view lists" and "q:quit" hints, allowing immediate exit on Esc/q.

## [0.1.2]
- Add support for `-h` / `--help` CLI help menus using Rich formatting.
- Add command aliases allowing prefix hyphens (e.g. `td -add`, `td -list`).
- Add Up/Down arrow key controls to easily increment/decrement the "max tasks" setting.
- Enforce strict bounds (3 to 15) for the "max tasks" preference.
- Display "already up-to-date." in update status when no updates are found.

## [0.1.1]
- Minimal TUI todo app launch.
