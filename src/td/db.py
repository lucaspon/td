from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".td.db"

MAX_ACTIVE_TASKS = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    position    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    done_at     TEXT,
    archived_at TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def get_active_tasks() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, status, position FROM tasks "
            "WHERE status != 'archived' ORDER BY position"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_archived_tasks() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, created_at, done_at, archived_at FROM tasks "
            "WHERE status = 'archived' ORDER BY archived_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_task(text: str) -> dict | None:
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        if count >= MAX_ACTIVE_TASKS:
            return None
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        now = _now_iso()
        cursor = conn.execute(
            "INSERT INTO tasks (text, position, created_at) VALUES (?, ?, ?)",
            (text, max_pos + 1, now),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "text": text, "status": "active", "position": max_pos + 1}
    finally:
        conn.close()


def update_task_text(task_id: int, text: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE tasks SET text = ? WHERE id = ?", (text, task_id))
        conn.commit()
    finally:
        conn.close()


def toggle_done(task_id: int) -> None:
    conn = _connect()
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return
        if row["status"] == "active":
            conn.execute(
                "UPDATE tasks SET status = 'done', done_at = ? WHERE id = ?",
                (_now_iso(), task_id),
            )
        elif row["status"] == "done":
            conn.execute(
                "UPDATE tasks SET status = 'active', done_at = NULL WHERE id = ?",
                (task_id,),
            )
        conn.commit()
    finally:
        conn.close()


def delete_task(task_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        _reorder_positions(conn)
        conn.commit()
    finally:
        conn.close()


def archive_done() -> int:
    conn = _connect()
    try:
        now = _now_iso()
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'done'"
        ).fetchone()[0]
        conn.execute(
            "UPDATE tasks SET status = 'archived', archived_at = ? WHERE status = 'done'",
            (now,),
        )
        _reorder_positions(conn)
        conn.commit()
        return count
    finally:
        conn.close()


def move_task(task_id: int, direction: int) -> None:
    """Move a task up (direction=-1) or down (direction=+1) in position."""
    conn = _connect()
    try:
        tasks = conn.execute(
            "SELECT id, position FROM tasks WHERE status != 'archived' ORDER BY position"
        ).fetchall()
        task_map = {t["id"]: t["position"] for t in tasks}
        if task_id not in task_map:
            return
        current_pos = task_map[task_id]
        # Find the task at the target position
        target_pos = current_pos + direction
        other_id = None
        for tid, pos in task_map.items():
            if pos == target_pos:
                other_id = tid
                break
        if other_id is None:
            return
        conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (target_pos, task_id))
        conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (current_pos, other_id))
        conn.commit()
    finally:
        conn.close()


def duplicate_task(task_id: int, direction: int) -> dict | None:
    """Duplicate a task. direction=-1 inserts above, direction=+1 inserts below."""
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        if count >= MAX_ACTIVE_TASKS:
            return None
        row = conn.execute(
            "SELECT text, status, position FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        # Shift positions to make room
        target_pos = row["position"] + direction
        if direction == -1:
            # Inserting above: shift everything at target_pos and above up by 1
            conn.execute(
                "UPDATE tasks SET position = position + 1 WHERE position >= ? AND status != 'archived'",
                (target_pos,),
            )
        else:
            # Inserting below: shift everything after current position up by 1
            conn.execute(
                "UPDATE tasks SET position = position + 1 WHERE position > ? AND status != 'archived'",
                (row["position"],),
            )
        now = _now_iso()
        cursor = conn.execute(
            "INSERT INTO tasks (text, status, position, created_at) VALUES (?, ?, ?, ?)",
            (row["text"], row["status"], target_pos, now),
        )
        _reorder_positions(conn)
        conn.commit()
        return {"id": cursor.lastrowid, "text": row["text"], "status": row["status"], "position": target_pos}
    finally:
        conn.close()


def restore_task(task_id: int) -> bool:
    """Restore an archived task to active. Returns False if no slots available."""
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        if count >= MAX_ACTIVE_TASKS:
            return False
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        conn.execute(
            "UPDATE tasks SET status = 'active', position = ?, done_at = NULL, archived_at = NULL WHERE id = ?",
            (max_pos + 1, task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def clear_archived() -> int:
    """Delete all archived tasks. Returns count deleted."""
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'archived'"
        ).fetchone()[0]
        conn.execute("DELETE FROM tasks WHERE status = 'archived'")
        conn.commit()
        return count
    finally:
        conn.close()


def get_completed_count() -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('done', 'archived')"
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def _reorder_positions(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id FROM tasks WHERE status != 'archived' ORDER BY position"
    ).fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (idx, row["id"]))