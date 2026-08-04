# td

A fast, keyboard-driven terminal manager for tasks and Markdown notes. Multi-list,
encrypted, scriptable, and built for humans and agents.

![td demo](assets/demo.gif)

## Install

```bash
uv tool install td-task   # recommended
```

Or with pip:

```bash
pip install td-task
```

## Local publishing environment

PyPI credentials live in the ignored `.env` file. The encrypted backup is
`.env.enc`.

```nu
^age --decrypt .env.enc | save --force .env
```

Never print decrypted secrets or commit `.env`.

Run directly without installing:

```bash
uvx td-task
```

For the `--dev` file watcher, install the optional extra:

```bash
uv tool install 'td-task[dev-mode]'
```

## Usage

```
td [command] [--list <name>]
```

| Command | Description |
|---------|-------------|
| `td` | Open the TUI (defaults to first list) |
| `td add <text>` | Add a task to a list |
| `td list` | Print active tasks to stdout |
| `td notes …` | Create, inspect, update, list, and delete Markdown notes |
| `td archive` | Open the archive screen |
| `td export [file]` | Export database to JSON (stdout if no file) |
| `td import <file>` | Merge a JSON backup into the database |
| `td update` | Upgrade to the latest version |
| `td --version` | Print the installed version |
| `td --help` | Print the help menu |

The `-l` / `--list` flag scopes a command to a specific list. It is required for `add`, `list`, and `archive`.

```bash
td -l work                      # open TUI locked to the "work" list
td add "fix the flaky test" -l work
td list --list work
td export backup.json
```

### Notes CLI

Notes use the same lists, ordering, completion state, archives, and encryption as
tasks. Every command supports stable note IDs. Add `--json` for structured output.

```bash
# create with inline Markdown
td notes add "Release plan" -l work --body $'# Release\n* test\n* ship' --json

# create from a file or stdin
td notes add "Runbook" -l ops --body-file runbook.md
cat incident.md | td notes add "Incident" -l ops --body-file -

# discover and read notes
td notes list -l work --json
td notes show 12
td notes show 12 --json

# update title or body
td notes update 12 --title "Final release plan"
td notes update 12 --body-file plan.md --json

# delete note and its task-backed list item
td notes delete 12 --json
```

`td notes add` uses the current timestamp when you omit the title. Pass
`--include-archived` to `td notes list` when agents need archived notes too.

## TUI Keybindings

### Tasks

| Key | Action |
|-----|--------|
| `a` | Add new task |
| `A` | Add a task-backed Markdown note |
| `e` / `Enter` | Edit selected task or open selected note |
| `E` | Rename selected note |
| `d` | Delete selected task |
| `Space` | Toggle done / active |
| `s` | Star task (pin to top, bold yellow) |
| `c` | Archive all completed tasks |
| `y` | Copy task list to clipboard |
| `↑` / `k` &nbsp; `↓` / `j` | Navigate tasks |
| `Ctrl+↑` / `Ctrl+↓` | Reorder task position |
| `Alt+↑` / `Alt+↓` | Duplicate task above / below |
| `←` / `→` | Switch to previous / next list |
| `l` / `Tab` | Open Lists Menu |
| `Ctrl+P` | Fuzzy-search lists |
| `,` | Open archive screen |
| `/` | Open settings |
| `?` | Help screen |
| `q` / `Esc` | Quit |

### Note Editor

| Key | Action |
|-----|--------|
| `Esc` | Save and close |
| `Ctrl+S` | Save without closing |
| `Enter` | Insert a new line |
| `Alt+↑` / `Alt+↓` | Move current line up or down |
| `Cmd+Backspace` on macOS / `Ctrl+Backspace` elsewhere | Clear current line |
| `Tab` / `Shift+Tab` | Indent or outdent current line |
| Arrow keys / `Home` / `End` | Move cursor |
| `Backspace` / `Delete` | Delete text or join lines |

The active line shows raw Markdown. Other lines show a live preview. The editor
supports `#` headings, `*` bullets, `*bold*`, `**bold**`, and `_italic_` text.
`Alt+Left` / `Alt+Right` moves by word. `Alt+Backspace` deletes one word.
After a root bullet, `Enter` starts an indented continuation and keeps its bullet
marker. Press `Enter` or `Backspace` on an empty continuation to leave list mode.

### Lists Menu

| Key | Action |
|-----|--------|
| `Enter` | Switch to highlighted list |
| `a` | Create new list |
| `e` | Rename list |
| `A` | Archive list while preserving its items |
| `,` | Open archived lists |
| `d` | Delete list (with all its tasks) |
| `Shift+↑` / `Shift+↓` | Reorder list position |
| `↑` / `k` &nbsp; `↓` / `j` | Navigate lists |
| `q` / `Esc` | Quit |

### Archived Lists

| Key | Action |
|-----|--------|
| `Enter` / `r` | Restore highlighted list |
| `d` | Permanently delete highlighted list and its items |
| `↑` / `k` &nbsp; `↓` / `j` | Navigate archived lists |
| `q` / `Esc` | Return to active lists |

### Archive

| Key | Action |
|-----|--------|
| `↑` / `k` &nbsp; `↓` / `j` | Navigate |
| `r` | Restore task to active list |
| `d` | Delete task permanently |
| `c` | Clear all archived tasks |
| `q` / `Esc` | Return to tasks |

### Settings

| Key | Action |
|-----|--------|
| `e` / `Enter` | Edit selected setting |
| `↑` / `↓` | Adjust numeric values (when editing) |
| `↑` / `k` &nbsp; `↓` / `j` | Navigate settings |
| `q` / `Esc` | Return |

Settings you can change: max tasks per list (3–50), max starred tasks, whole-database
encryption, current-list encryption, and backup export / import.

## Agent-friendly

`td` works well as a task layer for AI agents and shell scripts. The CLI commands are designed for scripting:

```bash
# add tasks from a script or agent
td add "review PR #42" -l work
td add "update dependencies" -l work

# read tasks as plain text
td list -l work

# create and query Markdown notes as JSON
td notes add "PR review" -l work --body "# Findings" --json
td notes list -l work --json
td notes show 1 --json

# dump the full database as JSON
td export | jq '.tasks[] | select(.status == "active")'

# point at a separate database — useful for testing or sandboxing
TD_DB_PATH=/tmp/agent.db td add "isolated task" -l inbox
```

The `--help` output is written to be LLM-readable, so agents can self-orient by running `td --help`.

## Stack

- **Python 3.14+** — application and CLI runtime.
- **SQLite** — single-file storage for lists, tasks, notes, settings, and encryption metadata.
- **Rich + raw ANSI terminal I/O** — styled rendering and keyboard input without a TUI framework.
- **Cryptography** — Fernet encryption with PBKDF2-derived database or per-list keys.
- **uv + Hatchling** — dependency management, builds, and Python packaging.

## Architecture

`td` is a single Python package with no framework dependencies:

| File | Role |
|------|------|
| `__main__.py` | CLI entry point, argument parsing, non-TUI commands |
| `tui.py` | Raw terminal render loop, all keybinding logic |
| `db.py` | SQLite layer — all reads and writes go through here |
| `terminal.py` | Low-level raw mode I/O and key decoding |

The TUI uses raw ANSI escape sequences directly rather than Curses or Textual. This keeps startup instant and the binary small.

Runtime dependencies: `rich` (terminal rendering), `cryptography` (AES encryption). `watchdog` is optional (`[dev-mode]` extra).

Works on macOS, Linux, and Windows. On Windows, use a terminal with ANSI support such as Windows Terminal for the best experience.

## Data model

Four core tables in a SQLite file:

**`lists`** — `name` (PK), `position`, `max_tasks`, `archived_at`

**`tasks`** — `id`, `text`, `status` (`active` / `done` / `archived`), `position`, `created_at`, `done_at`, `archived_at`, `starred`, `list_name` (FK → lists, CASCADE DELETE)

**`notes`** — `id`, `task_id` (unique FK → tasks, CASCADE DELETE), `title`, `content`, `created_at`, `updated_at`

**`list_encryption`** — `list_name` (PK/FK → lists), `encryption_salt`, `password_verifier`

Each note attaches to a task. It therefore shares task ordering, completion,
starring, archiving, and list membership. Note names appear underlined in lists.
Deleting a task or list also deletes attached notes through cascades.

Archived lists keep all tasks and notes. They disappear from normal navigation
until restored from the Lists Menu.

## Portability

Everything lives in `~/.td.db` — a single SQLite file you can copy, back up, or move between machines.

```bash
# override the database path
export TD_DB_PATH=~/Dropbox/td.db

# back up
td export > backup.json

# restore on another machine
td import backup.json
```

You can encrypt the whole database or only the current list from settings (`/`).
Each encrypted list uses its own password-derived key. Tasks and note bodies stay
encrypted in JSON backups. Whole-database and per-list encryption cannot run
together. If you forget a password, there is no recovery.
