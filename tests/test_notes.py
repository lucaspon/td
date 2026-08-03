from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from td import db


class NoteDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        self.original_key = db.ENCRYPTION_KEY
        self.original_list_keys = db.LIST_ENCRYPTION_KEYS.copy()
        db.DB_PATH = Path(self.temp_dir.name) / "td.db"
        db.ENCRYPTION_KEY = None
        db.LIST_ENCRYPTION_KEYS.clear()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_path
        db.ENCRYPTION_KEY = self.original_key
        db.LIST_ENCRYPTION_KEYS.clear()
        db.LIST_ENCRYPTION_KEYS.update(self.original_list_keys)
        self.temp_dir.cleanup()

    def test_note_uses_task_lifecycle_and_cascade(self) -> None:
        note = db.add_note("Planning", "work")
        self.assertIsNotNone(note)
        assert note is not None

        db.update_note_content(note["id"], "# Plan\n* first\n*second* and _later_")
        item = db.get_active_tasks("work")[0]
        self.assertTrue(item["is_note"])
        self.assertEqual(item["text"], "Planning")

        db.toggle_done(note["task_id"])
        db.archive_done("work")
        archived = db.get_archived_tasks("work")
        self.assertTrue(archived[0]["is_note"])

        db.delete_task(note["task_id"])
        self.assertIsNone(db.get_note(note["id"]))

    def test_rename_duplicate_and_backup_round_trip(self) -> None:
        note = db.add_note("Original", "main")
        self.assertIsNotNone(note)
        assert note is not None
        db.update_note_title(note["id"], "Renamed")
        db.update_note_content(note["id"], "body")
        db.duplicate_task(note["task_id"], 1)

        items = db.get_active_tasks("main")
        self.assertEqual([item["text"] for item in items], ["Renamed", "Renamed"])
        self.assertTrue(all(item["is_note"] for item in items))

        payload = json.loads(db.export_to_json())
        self.assertEqual(len(payload["notes"]), 2)
        self.assertEqual(payload["notes"][0]["content"], "body")

        db.DB_PATH = Path(self.temp_dir.name) / "imported.db"
        db.import_from_json(json.dumps(payload))
        imported = db.get_active_tasks("main")
        self.assertEqual(len(imported), 2)
        self.assertTrue(all(item["is_note"] for item in imported))

    def test_encryption_covers_note_title_and_content(self) -> None:
        note = db.add_note("Private title", "main")
        self.assertIsNotNone(note)
        assert note is not None
        db.update_note_content(note["id"], "Private body")

        db.enable_encryption("test-password")
        conn = db._connect()
        try:
            stored = conn.execute(
                "SELECT title, content FROM notes WHERE id = ?", (note["id"],)
            ).fetchone()
        finally:
            conn.close()
        self.assertNotEqual(stored["title"], "Private title")
        self.assertNotEqual(stored["content"], "Private body")
        self.assertEqual(db.get_note(note["id"])["content"], "Private body")

        self.assertTrue(db.disable_encryption("test-password"))
        self.assertEqual(db.get_note(note["id"])["title"], "Private title")

    def test_list_encryption_isolated_unlock_and_disable(self) -> None:
        note = db.add_note("Private note", "work")
        task = db.add_task("Private task", "work")
        public = db.add_task("Public task", "main")
        assert note is not None and task is not None and public is not None
        db.update_note_content(note["id"], "Private body")

        db.enable_list_encryption("work", "work-password")
        added_after_lock = db.add_task("Added later", "work")
        assert added_after_lock is not None
        db.update_note_content(note["id"], "Updated private body")
        conn = db._connect()
        try:
            stored_private = conn.execute(
                "SELECT text FROM tasks WHERE id = ?", (task["id"],)
            ).fetchone()["text"]
            stored_public = conn.execute(
                "SELECT text FROM tasks WHERE id = ?", (public["id"],)
            ).fetchone()["text"]
            stored_added = conn.execute(
                "SELECT text FROM tasks WHERE id = ?", (added_after_lock["id"],)
            ).fetchone()["text"]
        finally:
            conn.close()
        self.assertNotEqual(stored_private, "Private task")
        self.assertNotEqual(stored_added, "Added later")
        self.assertEqual(stored_public, "Public task")

        db.LIST_ENCRYPTION_KEYS.clear()
        with self.assertRaisesRegex(ValueError, "locked"):
            db.get_active_tasks("work")
        self.assertFalse(db.set_list_encryption_key_from_password("work", "wrong"))
        self.assertTrue(db.set_list_encryption_key_from_password("work", "work-password"))
        self.assertEqual(db.get_note(note["id"])["content"], "Updated private body")

        self.assertFalse(db.disable_list_encryption("work", "wrong"))
        self.assertTrue(db.disable_list_encryption("work", "work-password"))
        self.assertEqual(db.get_active_tasks("work")[1]["text"], "Private task")

    def test_list_encryption_backup_stays_protected(self) -> None:
        note = db.add_note("Secret", "vault")
        assert note is not None
        db.update_note_content(note["id"], "Hidden body")
        db.enable_list_encryption("vault", "vault-password")

        payload = db.export_to_json()
        self.assertNotIn("Hidden body", payload)
        self.assertNotIn('"title": "Secret"', payload)

        db.DB_PATH = Path(self.temp_dir.name) / "encrypted-restore.db"
        db.LIST_ENCRYPTION_KEYS.clear()
        db.import_from_json(payload)
        self.assertTrue(db.is_list_encryption_enabled("vault"))
        with self.assertRaisesRegex(ValueError, "locked"):
            db.get_active_tasks("vault")
        self.assertTrue(db.set_list_encryption_key_from_password("vault", "vault-password"))
        restored = db.get_active_tasks("vault")[0]
        self.assertEqual(restored["text"], "Secret")
        self.assertEqual(db.get_note(restored["note_id"])["content"], "Hidden body")

    def test_encrypted_list_can_be_renamed_and_archived(self) -> None:
        task = db.add_task("Secret", "work")
        assert task is not None
        db.enable_list_encryption("work", "password")

        self.assertTrue(db.rename_list("work", "private"))
        self.assertFalse(db.is_list_encryption_enabled("work"))
        self.assertTrue(db.is_list_encryption_enabled("private"))
        self.assertTrue(db.is_list_unlocked("private"))
        self.assertEqual(db.get_active_tasks("private")[0]["text"], "Secret")

        self.assertTrue(db.archive_list("private"))
        self.assertIn("private", [item["name"] for item in db.get_archived_lists()])

    def test_database_and_list_encryption_cannot_be_combined(self) -> None:
        db.create_list("work")
        db.enable_list_encryption("work", "password")
        with self.assertRaisesRegex(ValueError, "list encryption"):
            db.enable_encryption("database-password")

    def test_list_archive_preserves_and_restores_items(self) -> None:
        note = db.add_note("Planning", "work")
        task = db.add_task("Ship it", "work")
        self.assertIsNotNone(note)
        self.assertIsNotNone(task)

        self.assertTrue(db.archive_list("work"))
        self.assertNotIn("work", db.get_all_lists())
        self.assertEqual(db.get_archived_lists()[0]["name"], "work")
        self.assertEqual(len(db.get_active_tasks("work")), 2)

        payload = json.loads(db.export_to_json())
        work_list = next(item for item in payload["lists"] if item["name"] == "work")
        self.assertIsNotNone(work_list["archived_at"])

        self.assertTrue(db.restore_list("work"))
        self.assertIn("work", db.get_all_lists())
        self.assertFalse(db.get_archived_lists())
        self.assertEqual(len(db.get_active_tasks("work")), 2)

    def test_creating_archived_list_name_restores_it(self) -> None:
        db.create_list("later")
        self.assertTrue(db.archive_list("later"))

        db.create_list("later")

        self.assertIn("later", db.get_all_lists())
        self.assertFalse(db.get_archived_lists())

    def test_deleting_archived_list_cascades_to_notes(self) -> None:
        note = db.add_note("Disposable", "later")
        assert note is not None
        self.assertTrue(db.archive_list("later"))

        self.assertTrue(db.delete_list("later"))

        self.assertIsNone(db.get_note(note["id"]))
        self.assertFalse(db.get_archived_lists())

    def test_backup_round_trip_keeps_list_archived(self) -> None:
        note = db.add_note("Stored", "vault")
        assert note is not None
        self.assertTrue(db.archive_list("vault"))
        payload = db.export_to_json()

        db.DB_PATH = Path(self.temp_dir.name) / "restored.db"
        db.import_from_json(payload)

        archived_names = [item["name"] for item in db.get_archived_lists()]
        self.assertIn("vault", archived_names)
        items = db.get_active_tasks("vault")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["is_note"])

    def test_existing_database_migrates_list_archive_column(self) -> None:
        conn = sqlite3.connect(db.DB_PATH)
        try:
            conn.execute(
                "CREATE TABLE lists ("
                "name TEXT PRIMARY KEY, position INTEGER NOT NULL DEFAULT 0, max_tasks INTEGER)"
            )
            conn.execute("INSERT INTO lists (name) VALUES ('main')")
            conn.commit()
        finally:
            conn.close()

        migrated = db._connect()
        try:
            columns = {
                row["name"] for row in migrated.execute("PRAGMA table_info(lists)").fetchall()
            }
        finally:
            migrated.close()
        self.assertIn("archived_at", columns)


if __name__ == "__main__":
    unittest.main()
