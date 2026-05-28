from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".td.db"

DEFAULT_MAX_TASKS = 15
DEFAULT_MAX_STARRED_TASKS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    name TEXT PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    max_tasks INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    position    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    done_at     TEXT,
    archived_at TEXT,
    starred     INTEGER NOT NULL DEFAULT 0,
    list_name   TEXT NOT NULL DEFAULT 'main' REFERENCES lists(name) ON DELETE CASCADE
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

    # Migration 1: insert default 'main' list if lists table is empty
    count = conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0]
    if count == 0:
        conn.execute("INSERT OR IGNORE INTO lists (name) VALUES ('main')")
        conn.commit()

    # Migration 2: check if 'starred' column exists in tasks table
    cursor = conn.execute("PRAGMA table_info(tasks)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "starred" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    # Migration 3: check if 'list_name' column exists in tasks table
    if "list_name" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN list_name TEXT NOT NULL DEFAULT 'main'")
        conn.commit()

    # Migration 4: check if 'position' column exists in lists table
    cursor = conn.execute("PRAGMA table_info(lists)")
    lists_columns = [row["name"] for row in cursor.fetchall()]
    if "position" not in lists_columns:
        conn.execute("ALTER TABLE lists ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        # Initialize positions for existing lists
        rows = conn.execute("SELECT name FROM lists ORDER BY CASE WHEN name = 'main' THEN 0 ELSE 1 END, name").fetchall()
        for idx, row in enumerate(rows):
            conn.execute("UPDATE lists SET position = ? WHERE name = ?", (idx, row["name"]))
        conn.commit()

    # Migration 5: check if 'max_tasks' column exists in lists table
    if "max_tasks" not in lists_columns:
        conn.execute("ALTER TABLE lists ADD COLUMN max_tasks INTEGER")
        conn.commit()

    return conn


def create_list(name: str) -> None:
    cleaned = name.strip()
    if not cleaned:
        return
    conn = _connect()
    try:
        row = conn.execute("SELECT MAX(position) as max_pos FROM lists").fetchone()
        next_pos = (row["max_pos"] or 0) + 1 if row and row["max_pos"] is not None else 0
        conn.execute("INSERT OR IGNORE INTO lists (name, position) VALUES (?, ?)", (cleaned, next_pos))
        conn.commit()
    finally:
        conn.close()


def get_all_lists() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name FROM lists ORDER BY position, name"
        ).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


def move_list(name: str, direction: int) -> None:
    """Move list position by direction (-1 for left, 1 for right)."""
    conn = _connect()
    try:
        lists = conn.execute("SELECT name, position FROM lists ORDER BY position").fetchall()
        names = [r["name"] for r in lists]
        if name not in names:
            return
        idx = names.index(name)
        new_idx = idx + direction
        if 0 <= new_idx < len(names):
            p1 = lists[idx]["position"]
            p2 = lists[new_idx]["position"]
            conn.execute("UPDATE lists SET position = ? WHERE name = ?", (p2, name))
            conn.execute("UPDATE lists SET position = ? WHERE name = ?", (p1, names[new_idx]))
            conn.commit()
    finally:
        conn.close()


def rename_list(old_name: str, new_name: str) -> bool:
    old_clean = old_name.strip()
    new_clean = new_name.strip()
    if not old_clean or not new_clean or old_clean == new_clean:
        return False
    conn = _connect()
    try:
        exists = conn.execute("SELECT name FROM lists WHERE name = ?", (new_clean,)).fetchone()
        if exists:
            return False
        row = conn.execute("SELECT position FROM lists WHERE name = ?", (old_clean,)).fetchone()
        if not row:
            return False
        pos = row["position"]
        conn.execute("INSERT INTO lists (name, position) VALUES (?, ?)", (new_clean, pos))
        conn.execute("UPDATE tasks SET list_name = ? WHERE list_name = ?", (new_clean, old_clean))
        conn.execute("DELETE FROM lists WHERE name = ?", (old_clean,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_list(name: str) -> bool:
    cleaned = name.strip()
    if not cleaned:
        return False
    conn = _connect()
    try:
        conn.execute("DELETE FROM tasks WHERE list_name = ?", (cleaned,))
        conn.execute("DELETE FROM lists WHERE name = ?", (cleaned,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def export_to_json() -> str:
    import json
    conn = _connect()
    try:
        lists_cursor = conn.execute("SELECT name, position, max_tasks FROM lists ORDER BY position").fetchall()
        lists_data = [{"name": r["name"], "position": r["position"], "max_tasks": r["max_tasks"]} for r in lists_cursor]
        
        tasks_cursor = conn.execute(
            "SELECT id, text, status, position, created_at, done_at, archived_at, starred, list_name FROM tasks"
        ).fetchall()
        tasks_data = []
        for r in tasks_cursor:
            txt = r["text"]
            if is_encryption_enabled():
                try:
                    txt = _decrypt(txt)
                except Exception:
                    pass
            tasks_data.append({
                "id": r["id"],
                "text": txt,
                "status": r["status"],
                "position": r["position"],
                "created_at": r["created_at"],
                "done_at": r["done_at"],
                "archived_at": r["archived_at"],
                "starred": r["starred"],
                "list_name": r["list_name"]
            })
            
        settings_cursor = conn.execute("SELECT key, value FROM settings").fetchall()
        settings_data = {r["key"]: r["value"] for r in settings_cursor}
        
        pref_settings = {}
        for k, v in settings_data.items():
            if k not in ("encryption_enabled", "encryption_salt", "password_verifier"):
                pref_settings[k] = v
                
        payload = {
            "lists": lists_data,
            "tasks": tasks_data,
            "settings": pref_settings
        }
        return json.dumps(payload, indent=2)
    finally:
        conn.close()


def import_from_json(json_str: str) -> None:
    import json
    payload = json.loads(json_str)
    
    conn = _connect()
    try:
        conn.execute("BEGIN TRANSACTION")
        
        if "lists" in payload:
            for lst in payload["lists"]:
                name = lst.get("name", "").strip()
                if name:
                    pos = lst.get("position", 0)
                    m_tasks = lst.get("max_tasks")
                    conn.execute("INSERT OR REPLACE INTO lists (name, position, max_tasks) VALUES (?, ?, ?)", (name, pos, m_tasks))
                    
        if "tasks" in payload:
            for tsk in payload["tasks"]:
                tid = tsk.get("id")
                text = tsk.get("text", "")
                status = tsk.get("status", "active")
                pos = tsk.get("position", 0)
                created_at = tsk.get("created_at", _now_iso())
                done_at = tsk.get("done_at")
                archived_at = tsk.get("archived_at")
                starred = tsk.get("starred", 0)
                list_name = tsk.get("list_name", "main")
                
                conn.execute("INSERT OR IGNORE INTO lists (name, position) VALUES (?, 0)", (list_name,))
                
                db_text = _encrypt(text) if is_encryption_enabled() else text
                
                conn.execute(
                    "INSERT OR REPLACE INTO tasks (id, text, status, position, created_at, done_at, archived_at, starred, list_name) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tid, db_text, status, pos, created_at, done_at, archived_at, starred, list_name)
                )
                
        if "settings" in payload:
            for k, v in payload["settings"].items():
                if k not in ("encryption_enabled", "encryption_salt", "password_verifier"):
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
                    
        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        raise e
    finally:
        conn.close()


def get_max_tasks(list_name: str | None = None) -> int:
    conn = _connect()
    try:
        if list_name:
            row = conn.execute("SELECT max_tasks FROM lists WHERE name = ?", (list_name,)).fetchone()
            if row and row["max_tasks"] is not None:
                return int(row["max_tasks"])
        
        row = conn.execute("SELECT value FROM settings WHERE key = 'max_tasks'").fetchone()
        if row:
            return int(row["value"])
        return DEFAULT_MAX_TASKS
    finally:
        conn.close()


def set_max_tasks(value: int, list_name: str | None = None) -> None:
    conn = _connect()
    try:
        if list_name:
            conn.execute(
                "UPDATE lists SET max_tasks = ? WHERE name = ?",
                (value, list_name),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('max_tasks', ?)",
                (str(value),),
            )
        conn.commit()
    finally:
        conn.close()


def get_max_starred_tasks() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'max_starred_tasks'").fetchone()
        if row:
            return int(row["value"])
        return DEFAULT_MAX_STARRED_TASKS
    finally:
        conn.close()


def set_max_starred_tasks(value: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('max_starred_tasks', ?)",
            (str(value),),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_tasks(list_name: str = "main") -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, status, position, starred, list_name FROM tasks "
            "WHERE status != 'archived' AND list_name = ? ORDER BY position",
            (list_name,),
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


def get_archived_tasks(list_name: str = "main") -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, text, created_at, done_at, archived_at, list_name FROM tasks "
            "WHERE status = 'archived' AND list_name = ? ORDER BY archived_at DESC",
            (list_name,),
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


def add_task(text: str, list_name: str = "main") -> dict | None:
    create_list(list_name)
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        if count >= get_max_tasks(list_name):
            return None
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        now = _now_iso()
        db_text = _encrypt(text) if is_encryption_enabled() else text
        cursor = conn.execute(
            "INSERT INTO tasks (text, position, created_at, starred, list_name) VALUES (?, ?, ?, 0, ?)",
            (db_text, max_pos + 1, now, list_name),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "text": text,
            "status": "active",
            "position": max_pos + 1,
            "starred": 0,
            "list_name": list_name,
        }
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
        row = conn.execute("SELECT status, list_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return
        list_name = row["list_name"]
        if row["status"] == "active":
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived' AND list_name = ?",
                (list_name,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE tasks SET status = 'done', done_at = ?, position = ? WHERE id = ?",
                (_now_iso(), max_pos + 1, task_id),
            )
            _reorder_positions(conn, list_name)
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
        row = conn.execute("SELECT list_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            list_name = row["list_name"]
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            _reorder_positions(conn, list_name)
            conn.commit()
    finally:
        conn.close()


def archive_done(list_name: str = "main") -> int:
    conn = _connect()
    try:
        now = _now_iso()
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'done' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE tasks SET status = 'archived', archived_at = ? WHERE status = 'done' AND list_name = ?",
            (now, list_name),
        )
        _reorder_positions(conn, list_name)
        conn.commit()
        return count
    finally:
        conn.close()


def move_task(task_id: int, direction: int) -> None:
    """Move a task up (direction=-1) or down (direction=+1) in position."""
    conn = _connect()
    try:
        row = conn.execute("SELECT list_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return
        list_name = row["list_name"]
        tasks = conn.execute(
            "SELECT id, position, starred FROM tasks WHERE status != 'archived' AND list_name = ? ORDER BY position",
            (list_name,),
        ).fetchall()
        task_map = {t["id"]: (t["position"], t["starred"]) for t in tasks}
        if task_id not in task_map:
            return
        current_pos, current_starred = task_map[task_id]
        # Find the task at the target position
        target_pos = current_pos + direction
        other_id = None
        other_starred = None
        for tid, (pos, starred) in task_map.items():
            if pos == target_pos:
                other_id = tid
                other_starred = starred
                break
        if other_id is None:
            return
        if current_starred == other_starred:
            conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (target_pos, task_id))
            conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (current_pos, other_id))
            conn.commit()
    finally:
        conn.close()


def duplicate_task(task_id: int, direction: int) -> dict | None:
    """Duplicate a task. direction=-1 inserts above, direction=+1 inserts below."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT text, status, position, starred, list_name FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        list_name = row["list_name"]
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        if count >= get_max_tasks(list_name):
            return None
        # Shift positions to make room
        target_pos = row["position"] + direction
        if direction == -1:
            # Inserting above: shift everything at target_pos and above up by 1
            conn.execute(
                "UPDATE tasks SET position = position + 1 WHERE position >= ? AND status != 'archived' AND list_name = ?",
                (target_pos, list_name),
            )
        else:
            # Inserting below: shift everything after current position up by 1
            conn.execute(
                "UPDATE tasks SET position = position + 1 WHERE position > ? AND status != 'archived' AND list_name = ?",
                (row["position"], list_name),
            )
        now = _now_iso()
        db_text = row["text"]
        plaintext = _decrypt(db_text) if is_encryption_enabled() else db_text
        cursor = conn.execute(
            "INSERT INTO tasks (text, status, position, created_at, starred, list_name) VALUES (?, ?, ?, ?, ?, ?)",
            (db_text, row["status"], target_pos, now, row["starred"], list_name),
        )
        _reorder_positions(conn, list_name)
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "text": plaintext,
            "status": row["status"],
            "position": target_pos,
            "starred": row["starred"],
            "list_name": list_name,
        }
    finally:
        conn.close()


def restore_task(task_id: int) -> bool:
    """Restore an archived task to active. Returns False if no slots available."""
    conn = _connect()
    try:
        row = conn.execute("SELECT list_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return False
        list_name = row["list_name"]
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        if count >= get_max_tasks(list_name):
            return False
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE status != 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE tasks SET status = 'active', position = ?, done_at = NULL, archived_at = NULL, starred = 0 WHERE id = ?",
            (max_pos + 1, task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def clear_archived(list_name: str = "main") -> int:
    """Delete all archived tasks for a list. Returns count deleted."""
    conn = _connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'archived' AND list_name = ?",
            (list_name,),
        ).fetchone()[0]
        conn.execute("DELETE FROM tasks WHERE status = 'archived' AND list_name = ?", (list_name,))
        conn.commit()
        return count
    finally:
        conn.close()


def get_completed_count(list_name: str = "main") -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('done', 'archived') AND list_name = ?",
            (list_name,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def toggle_starred(task_id: int) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT starred, list_name FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return False
        list_name = row["list_name"]
        if row["starred"] == 0:
            count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status != 'archived' AND starred = 1 AND list_name = ?",
                (list_name,),
            ).fetchone()[0]
            if count >= get_max_starred_tasks():
                return False
            new_starred = 1
        else:
            new_starred = 0
        conn.execute("UPDATE tasks SET starred = ? WHERE id = ?", (new_starred, task_id))
        _reorder_positions(conn, list_name)
        conn.commit()
        return True
    finally:
        conn.close()


def _reorder_positions(conn: sqlite3.Connection, list_name: str) -> None:
    rows = conn.execute(
        "SELECT id FROM tasks WHERE status != 'archived' AND list_name = ? ORDER BY starred DESC, position",
        (list_name,),
    ).fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE tasks SET position = ? WHERE id = ?", (idx, row["id"]))