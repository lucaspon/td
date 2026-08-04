from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from td import db, terminal, tui


class NoteTuiTests(unittest.TestCase):
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

    def _edit_note(self, note_id: int, keys: list[str]) -> None:
        output = io.StringIO()
        test_console = Console(file=output, width=80, height=20, force_terminal=False)
        key_stream = iter(keys)
        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(key_stream)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_note_editor(note_id)

    def test_capital_a_creates_and_opens_note(self) -> None:
        keys = iter([
            "A",
            terminal.KEY_ENTER,
            "#",
            " ",
            "H",
            terminal.KEY_ENTER,
            "*",
            " ",
            "i",
            terminal.KEY_ESC,
            "E",
            terminal.KEY_HOME,
            terminal.KEY_DELETE,
            terminal.KEY_DELETE,
            terminal.KEY_DELETE,
            "N",
            "e",
            "w",
            terminal.KEY_ENTER,
            "e",
            terminal.KEY_ESC,
            "q",
        ])
        output = io.StringIO()
        test_console = Console(file=output, width=80, height=20, force_terminal=False)

        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui, "_default_note_title", return_value="Old"),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_main_loop("main", lock_list=True)

        items = db.get_active_tasks("main")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["is_note"])
        note = db.get_note(items[0]["note_id"])
        self.assertEqual(note["title"], "New")
        self.assertEqual(note["content"], "# H\n* i")

    def test_markdown_preview_supports_requested_styles(self) -> None:
        heading = tui._markdown_preview_line("# Heading")
        bullet = tui._markdown_preview_line("* item")
        inline = tui._markdown_preview_line("*bold* and _italic_")

        self.assertEqual(heading.plain, "Heading")
        self.assertIn("bold", str(heading.spans[0].style))
        self.assertEqual(bullet.plain, "• item")
        self.assertEqual(inline.plain, "bold and italic")
        self.assertIn("bold", str(inline.spans[0].style))
        self.assertIn("italic", str(inline.spans[1].style))

    def test_note_editor_wrap_preserves_every_character(self) -> None:
        source = Text("alpha  beta gamma-supercalifragilistic", style="bold")
        wrapped = tui._wrap_editor_text(source, 8)

        self.assertEqual("".join(part.plain for part in wrapped), source.plain)
        self.assertTrue(all(cell_len(part.plain) <= 8 for part in wrapped))
        self.assertTrue(all("bold" in str(part.style) for part in wrapped))

    def test_note_editor_cursor_follows_wrapped_line(self) -> None:
        line = "one two three four five six"
        visual_rows, cursor_row = tui._note_editor_visual_rows(
            [line], 0, len(line), 7
        )

        self.assertGreater(len(visual_rows), 1)
        self.assertEqual(visual_rows[cursor_row][0], 0)
        self.assertTrue(any(
            "reverse" in str(span.style)
            for span in visual_rows[cursor_row][2].spans
        ))

    def test_note_editor_scroll_tracks_wrapped_cursor(self) -> None:
        note = db.add_note("Wrapping")
        assert note is not None
        db.update_note_content(note["id"], "word " * 40)
        scroll_positions: list[int] = []
        test_console = Console(file=io.StringIO(), width=30, height=10, force_terminal=False)
        keys = iter([terminal.KEY_END, terminal.KEY_ESC])

        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(terminal, "clear_screen"),
            patch.object(
                tui,
                "_render_note_editor",
                side_effect=lambda _title, _lines, _row, _column, scroll, _status: (
                    scroll_positions.append(scroll)
                ),
            ),
        ):
            tui._run_note_editor(note["id"])

        self.assertEqual(scroll_positions[0], 0)
        self.assertGreater(scroll_positions[-1], 0)

    def test_alt_arrows_move_editor_lines(self) -> None:
        note = db.add_note("Movement")
        assert note is not None
        db.update_note_content(note["id"], "first\nsecond word\nthird")

        self._edit_note(note["id"], [
            terminal.KEY_ALT_ARROW_DOWN,
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ALT_ARROW_UP,
            terminal.KEY_ESC,
        ])

        self.assertEqual(db.get_note(note["id"])["content"], "second word\nthird\nfirst")

    def test_indent_and_outdent_current_line(self) -> None:
        note = db.add_note("Indentation")
        assert note is not None
        db.update_note_content(note["id"], "item")

        self._edit_note(note["id"], ["\t", terminal.KEY_ESC])
        self.assertEqual(db.get_note(note["id"])["content"], "  item")

        self._edit_note(note["id"], [terminal.KEY_SHIFT_TAB, terminal.KEY_ESC])
        self.assertEqual(db.get_note(note["id"])["content"], "item")

    def test_bullets_auto_indent_and_continue(self) -> None:
        note = db.add_note("Bullets")
        assert note is not None
        db.update_note_content(note["id"], "* first")

        self._edit_note(note["id"], [
            terminal.KEY_END,
            terminal.KEY_ENTER,
            "s", "e", "c", "o", "n", "d",
            terminal.KEY_ENTER,
            terminal.KEY_ENTER,
            terminal.KEY_ESC,
        ])

        self.assertEqual(db.get_note(note["id"])["content"], "* first\n  * second\n")

    def test_backspace_stops_empty_bullet_continuation(self) -> None:
        note = db.add_note("Bullets")
        assert note is not None
        db.update_note_content(note["id"], "* first")

        self._edit_note(note["id"], [
            terminal.KEY_END,
            terminal.KEY_ENTER,
            terminal.KEY_BACKSPACE,
            "p", "l", "a", "i", "n",
            terminal.KEY_ESC,
        ])

        self.assertEqual(db.get_note(note["id"])["content"], "* first\nplain")

    def test_alt_word_navigation_and_deletion(self) -> None:
        note = db.add_note("Words")
        assert note is not None
        db.update_note_content(note["id"], "alpha beta")

        self._edit_note(note["id"], [
            terminal.KEY_END,
            terminal.KEY_ALT_ARROW_LEFT,
            "X",
            terminal.KEY_ALT_ARROW_RIGHT,
            "!",
            terminal.KEY_ALT_BACKSPACE,
            terminal.KEY_ESC,
        ])

        self.assertEqual(db.get_note(note["id"])["content"], "alpha ")

    def test_command_and_control_backspace_clear_line(self) -> None:
        note = db.add_note("Clear line")
        assert note is not None

        for clear_key in (terminal.KEY_CMD_BACKSPACE, terminal.KEY_CTRL_BACKSPACE):
            with self.subTest(clear_key=repr(clear_key)):
                db.update_note_content(note["id"], "clear me")
                self._edit_note(note["id"], [clear_key, terminal.KEY_ESC])
                self.assertEqual(db.get_note(note["id"])["content"], "")

    def test_list_menu_archives_and_restores_list(self) -> None:
        db.create_list("work")
        keys = iter([
            "l",
            terminal.KEY_ARROW_DOWN,
            "A",
            terminal.KEY_ENTER,
            ",",
            terminal.KEY_ENTER,
            "q",
            "q",
        ])
        output = io.StringIO()
        test_console = Console(file=output, width=100, height=24, force_terminal=False)

        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_main_loop("main")

        self.assertIn("work", db.get_all_lists())
        self.assertFalse(db.get_archived_lists())

    def test_app_opens_lists_menu_when_every_list_is_archived(self) -> None:
        self.assertTrue(db.archive_list("main"))
        keys = iter([",", terminal.KEY_ENTER, "q", "q"])
        output = io.StringIO()
        test_console = Console(file=output, width=100, height=24, force_terminal=False)

        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_main_loop("main")

        self.assertEqual(db.get_all_lists(), ["main"])
        self.assertFalse(db.get_archived_lists())

    def test_settings_toggles_current_list_encryption(self) -> None:
        db.add_task("Secret", "main")
        output = io.StringIO()
        test_console = Console(file=output, width=100, height=28, force_terminal=False)

        enable_keys = iter([
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ENTER,
            terminal.KEY_ENTER,
            "q",
        ])
        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(enable_keys)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui, "prompt_password", side_effect=["password", "password"]),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_settings_loop("main")
        self.assertTrue(db.is_list_encryption_enabled("main"))

        disable_keys = iter([
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ARROW_DOWN,
            terminal.KEY_ENTER,
            "q",
        ])
        with (
            patch.object(tui, "console", test_console),
            patch.object(terminal, "read_key", side_effect=lambda: next(disable_keys)),
            patch.object(terminal, "reset_cursor"),
            patch.object(terminal, "clear_screen"),
            patch.object(tui, "prompt_password", return_value="password"),
            patch.object(tui.sys.stdout, "write"),
            patch.object(tui.sys.stdout, "flush"),
        ):
            tui._run_settings_loop("main")
        self.assertFalse(db.is_list_encryption_enabled("main"))


if __name__ == "__main__":
    unittest.main()
