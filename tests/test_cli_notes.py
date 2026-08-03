from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from td import db
from td.__main__ import _run_notes


class NoteCliTests(unittest.TestCase):
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

    def _run(self, args: list[str], list_name: str = "work", has_list: bool = True) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            _run_notes(list_name, has_list, args)
        return output.getvalue()

    def test_note_crud_json_cli(self) -> None:
        created = json.loads(self._run([
            "td", "notes", "add", "Agent note", "--body", "# Plan\n* ship", "--json",
        ]))
        note_id = created["id"]

        listed = json.loads(self._run(["td", "notes", "list", "--json"]))
        self.assertEqual(listed[0]["id"], note_id)
        self.assertEqual(listed[0]["title"], "Agent note")

        shown = self._run(["td", "notes", "show", str(note_id)])
        self.assertEqual(shown, "# Plan\n* ship\n")

        updated = json.loads(self._run([
            "td", "notes", "update", str(note_id),
            "--title", "Updated", "--body", "done", "--json",
        ]))
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["content"], "done")

        deleted = json.loads(self._run([
            "td", "notes", "delete", str(note_id), "--json",
        ]))
        self.assertTrue(deleted["deleted"])
        self.assertIsNone(db.get_note(note_id))

    def test_note_body_accepts_file_and_stdin(self) -> None:
        body_path = Path(self.temp_dir.name) / "note.md"
        body_path.write_text("from file", encoding="utf-8")
        created = json.loads(self._run([
            "td", "notes", "add", "File note", "--body-file", str(body_path), "--json",
        ]))
        self.assertEqual(db.get_note(created["id"])["content"], "from file")

        with patch("sys.stdin", io.StringIO("from stdin")):
            created_stdin = json.loads(self._run([
                "td", "notes", "add", "Stdin note", "--body-file", "-", "--json",
            ]))
        self.assertEqual(db.get_note(created_stdin["id"])["content"], "from stdin")


if __name__ == "__main__":
    unittest.main()
