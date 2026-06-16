# td

A fast, keyboard-driven TUI todo manager for the terminal. Multi-list, encrypted, scriptable.

![td demo](assets/demo.gif)

## Install

```bash
uv tool install td-task   # recommended
```

Or with pip:

```bash
pip install td-task
```

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

## TUI Keybindings

### Tasks

| Key | Action |
|-----|--------|
| `a` | Add new task |
| `e` / `Enter` | Edit selected task |
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

### Lists Menu

| Key | Action |
|-----|--------|
| `Enter` | Switch to highlighted list |
| `a` | Create new list |
| `e` | Rename list |
| `d` | Delete list (with all its tasks) |
| `Shift+↑` / `Shift+↓` | Reorder list position |
| `↑` / `k` &nbsp; `↓` / `j` | Navigate lists |
| `q` / `Esc` | Quit |

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

Settings you can change: max tasks per list (3–50), max starred tasks, database encryption (AES), and backup export / import.

## Agent-friendly

`td` works well as a task layer for AI agents and shell scripts. The CLI commands are designed for scripting:

```bash
# add tasks from a script or agent
td add "review PR #42" -l work
td add "update dependencies" -l work

# read tasks as plain text
td list -l work

# dump the full database as JSON
td export | jq '.tasks[] | select(.status == "active")'

# point at a separate database — useful for testing or sandboxing
TD_DB_PATH=/tmp/agent.db td add "isolated task" -l inbox
```

The `--help` output is written to be LLM-readable, so agents can self-orient by running `td --help`.

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

Two tables in a SQLite file:

**`lists`** — `name` (PK), `position`, `max_tasks`

**`tasks`** — `id`, `text`, `status` (`active` / `done` / `archived`), `position`, `created_at`, `done_at`, `archived_at`, `starred`, `list_name` (FK → lists, CASCADE DELETE)

Tasks keep their timestamps through the full lifecycle: created → done → archived. Deleting a list permanently removes all its tasks via the cascade.

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

You can encrypt the database with a password from the settings screen (`/`). If you forget the password, there is no recovery — your tasks are gone.

## Show some love

Ethereum: `0x88a0e1b80B92F0cFaa89a936b827Ce291cFb0028`
