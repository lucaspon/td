# td

A fast, keyboard-driven TUI todo manager for the terminal. Multi-list, encrypted, scriptable.

```
td • work  • 3 open / 5 completed
────────────────────────────────
★ finish the README
▸ ○ write tests
  ○ push to prod
────────────────────────────────
  a:add │ e:edit │ d:delete │ Space:done │ s:star │ c:clear │ l:view lists │ q:quit │ ?:help
```

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

## Storage

Tasks live in `~/.td.db` — a single portable SQLite file. Delete it to start fresh.

You can encrypt the database with a password from the settings screen (`/`). If you forget the password, there is no recovery — your tasks are gone.

## Show some love

Ethereum: `0x88a0e1b80B92F0cFaa89a936b827Ce291cFb0028`
