# td

A minimal TUI todo CLI. No setup required — just run it.

## Install

```bash
pip install .
```

Or run directly with `uv`:

```bash
uv run td
```

## Usage

```bash
td          # Open the task manager
td archive  # View archived tasks
```

## Keybindings

| Key | Action |
|-----|--------|
| ↑/k | Move up |
| ↓/j | Move down |
| Enter | Edit hovered item |
| n | Add new task (max 10) |
| d | Delete hovered task |
| Space | Toggle done |
| a | Archive all done tasks |
| q | Quit |

In edit mode, type to modify text, Enter to confirm, Esc to cancel.

## Storage

Tasks are stored in `~/.td.db` (portable SQLite file). Delete it to start fresh.