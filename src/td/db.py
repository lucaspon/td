from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".td.db"

DEFAULT_MAX_TASKS = 15

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

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ENCRYPTION_KEY: bytes | None = None


def is_encryption_enabled() -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'encryption_enabled'").fetchone()
        return row is not None and row["value"] == "1"
    finally:
        conn.close()


def get_encryption_salt() -> bytes | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'encryption_salt'").fetchone()
        if row:
            import base64
            return base64.b64decode(row["value"])
        return None
    finally:
        conn.close()


def _derive_key(password: str, salt: bytes) -> bytes:
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def _verify_key(key: bytes) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'password_verifier'").fetchone()
        if not row:
            return False
        from cryptography.fernet import Fernet
        f = Fernet(key)
        decrypted = f.decrypt(row["value"].encode()).decode()
        return decrypted == "verification_token"
    except Exception:
        return False
    finally:
        conn.close()


def set_encryption_key_from_password(password: str) -> bool:
    global ENCRYPTION_KEY
    salt = get_encryption_salt()
    if salt is None:
        return False
    key = _derive_key(password, salt)
    if _verify_key(key):
        ENCRYPTION_KEY = key
        return True
    return False


def _encrypt(text: str) -> str:
    if not text:
        return ""
    if ENCRYPTION_KEY is None:
        raise ValueError("Database is encrypted but key is not loaded")
    from cryptography.fernet import Fernet
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(text.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    if ENCRYPTION_KEY is None:
        raise ValueError("Database is encrypted but key is not loaded")
    from cryptography.fernet import Fernet
    f = Fernet(ENCRYPTION_KEY)
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return "[Decryption Failed]"


def enable_encryption(password: str) -> None:
    import secrets
    import base64
    from cryptography.fernet import Fernet

    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt)

    conn = _connect()
    try:
        f = Fernet(key)
        verifier = f.encrypt(b"verification_token").decode()

        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('encryption_enabled', '1')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('encryption_salt', ?)", (base64.b64encode(salt).decode(),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('password_verifier', ?)", (verifier,))

        rows = conn.execute("SELECT id, text FROM tasks").fetchall()
        for row in rows:
            enc_text = f.encrypt(row["text"].encode()).decode()
            conn.execute("UPDATE tasks SET text = ? WHERE id = ?", (enc_text, row["id"]))

        conn.commit()
        global ENCRYPTION_KEY
        ENCRYPTION_KEY = key
    finally:
        conn.close()


def disable_encryption(password: str) -> bool:
    global ENCRYPTION_KEY
    salt = get_encryption_salt()
    if salt is None:
        return False
    key = _derive_key(password, salt)
    if not _verify_key(key):
        return False

    from cryptography.fernet import Fernet
    f = Fernet(key)

    conn = _connect()
    try:
        rows = conn.execute("SELECT id, text FROM tasks").fetchall()
        for row in rows:
            dec_text = f.decrypt(row["text"].encode()).decode()
            conn.execute("UPDATE tasks SET text = ? WHERE id = ?", (dec_text, row["id"]))

        conn.execute("DELETE FROM settings WHERE key IN ('encryption_enabled', 'encryption_salt', 'password_verifier')")
        conn.commit()
        ENCRYPTION_KEY = None
        return True
    finally:
        conn.close()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def get_max_tasks() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'max_tasks'").fetchone()
        if row:
            return int(row["value"])
        return DEFAULT_MAX_TASKS
    finally:
        conn.close()


def set_max_tasks(value: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('max_tasks', ?)",
            (str(value),),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_tasks() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, status, position FROM tasks "
            "WHERE status != 'archived' ORDER BY position"
        ).fetchall()
        tasks = []
        for r in rows:
            d = dict(r)
            if is_encryption_enabled():
                d["text"] = _decrypt(d["text"])
            tasks.append(d)
        return tasks
    finally:
        conn.close()


def get_archived_tasks() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, created_at, done_at, archived_at FROM tasks "
            "WHERE status = 'archived' ORDER BY archived_at DESC"
        ).fetchall()
        tasks = []
        for r in rows:
            d = dict(r)
            if is_encryption_enabled():
                d["text"] = _decrypt(d["text"])
            tasks.append(d)
        return tasks
    finally:
        conn.close()


def add_task(text: str) -> dict | None:
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        if count >= get_max_tasks():
            return None
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        now = _now_iso()
        db_text = _encrypt(text) if is_encryption_enabled() else text
        cursor = conn.execute(
            "INSERT INTO tasks (text, position, created_at) VALUES (?, ?, ?)",
            (db_text, max_pos + 1, now),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "text": text, "status": "active", "position": max_pos + 1}
    finally:
        conn.close()


def update_task_text(task_id: int, text: str) -> None:
    conn = _connect()
    try:
        db_text = _encrypt(text) if is_encryption_enabled() else text
        conn.execute("UPDATE tasks SET text = ? WHERE id = ?", (db_text, task_id))
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
        if count >= get_max_tasks():
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
        db_text = row["text"]
        plaintext = _decrypt(db_text) if is_encryption_enabled() else db_text
        cursor = conn.execute(
            "INSERT INTO tasks (text, status, position, created_at) VALUES (?, ?, ?, ?)",
            (db_text, row["status"], target_pos, now),
        )
        _reorder_positions(conn)
        conn.commit()
        return {"id": cursor.lastrowid, "text": plaintext, "status": row["status"], "position": target_pos}
    finally:
        conn.close()


def restore_task(task_id: int) -> bool:
    """Restore an archived task to active. Returns False if no slots available."""
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived'"
        ).fetchone()[0]
        if count >= get_max_tasks():
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