from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from td import db, terminal, tui

if not terminal.IS_WINDOWS:
    import pty
    import select
    import termios


class ResizeTuiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(db, "DB_PATH", Path(directory) / "td.db"))
        self.stack.enter_context(patch.object(db, "ENCRYPTION_KEY", None))
        self.stack.enter_context(patch.object(db, "LIST_ENCRYPTION_KEYS", {}))
        self.stack.enter_context(patch.dict(os.environ, {
            "TD_CONFIG_PATH": str(Path(directory) / "config.toml"),
        }))
        self.output = io.StringIO()
        self.console = Console(file=self.output, width=80, height=24, force_terminal=False)
        self.stack.enter_context(patch.object(tui, "console", self.console))
        self.stack.enter_context(patch.object(terminal, "clear_screen"))
        db.create_list("main")

    def test_resize_preserves_task_edit_and_cursor(self) -> None:
        keys = iter(["a", "x", terminal.KEY_RESIZE, "y", terminal.KEY_ENTER, "q"])
        states = []
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(tui, "_render_main", side_effect=lambda *args: states.append(args)),
        ):
            tui._run_main_loop("main", lock_list=True)

        self.assertEqual(db.get_active_tasks("main")[0]["text"], "xy")
        edited = [(state[2], state[3], state[4]) for state in states]
        self.assertIn(("edit", "x", 1), edited)
        self.assertEqual(edited.count(("edit", "x", 1)), 2)

    def test_resize_keeps_delete_confirmation_open(self) -> None:
        task = db.add_task("Keep this", "main")
        keys = iter(["d", terminal.KEY_RESIZE, terminal.KEY_ESC, "q"])
        modes = []
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(tui, "_render_main", side_effect=lambda *args: modes.append(args[2])),
        ):
            tui._run_main_loop("main", lock_list=True)

        self.assertEqual(modes, ["normal", "confirm", "confirm", "normal"])
        self.assertEqual(db.get_active_tasks("main")[0]["id"], task["id"])

    def test_resize_keeps_selection_visible_in_a_shorter_task_list(self) -> None:
        db.set_max_tasks(40, "main")
        for index in range(20):
            db.add_task(f"Task {index}", "main")
        keys = iter([terminal.KEY_ARROW_DOWN] * 12 + [terminal.KEY_RESIZE, "q"])
        states = []

        def read_key():
            key = next(keys)
            if key == terminal.KEY_RESIZE:
                self.console.width = 30
                self.console.height = 10
            return key

        with (
            patch.object(terminal, "read_key", side_effect=read_key),
            patch.object(tui, "_render_main", side_effect=lambda *args: states.append(args)),
        ):
            tui._run_main_loop("main", lock_list=True)

        self.assertEqual(states[-1][1], 12)
        self.assertGreater(states[-1][-3], states[-2][-3])

    def test_resize_keeps_help_open(self) -> None:
        keys = iter(["?", terminal.KEY_RESIZE, "x", "q"])
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(tui, "_render_help_screen") as render_help,
        ):
            tui._run_main_loop("main", lock_list=True)
        self.assertEqual(render_help.call_count, 2)

    def test_editor_resize_preserves_draft_and_reflows_scroll(self) -> None:
        note = db.add_note("Draft", "main")
        original = "word " * 40
        db.update_note_content(note["id"], original)
        keys = iter([
            terminal.KEY_END, "!", terminal.KEY_RESIZE, "?",
            terminal.KEY_RESIZE, terminal.KEY_ESC,
        ])
        states = []
        sizes = iter([(20, 8), (100, 30)])

        def read_key():
            key = next(keys)
            if key == terminal.KEY_RESIZE:
                self.console.width, self.console.height = next(sizes)
            return key

        with (
            patch.object(terminal, "read_key", side_effect=read_key),
            patch.object(tui, "_render_note_editor", side_effect=lambda *args: states.append(args)),
        ):
            tui._run_note_editor(note["id"])

        self.assertEqual(db.get_note(note["id"])["content"], original + "!?")
        self.assertEqual(states[3][2:4], states[2][2:4])
        self.assertGreater(states[3][4], 0)
        self.assertEqual(states[-1][4], 0)

    def test_small_settings_frame_shows_selected_item_and_footer(self) -> None:
        self.console.width = 30
        self.console.height = 10
        tui._render_settings("main", hover=6)
        text = Text.from_ansi(self.output.getvalue()).plain
        self.assertIn("▸ import database", text)
        self.assertIn("navigate", text)
        self.assertLessEqual(len(text.splitlines()), 10)
        self.assertTrue(all(cell_len(line) <= 30 for line in text.splitlines()))

    def test_small_editor_frame_fits_actual_dimensions(self) -> None:
        self.console.width = 20
        self.console.height = 8
        tui._render_note_editor("Long title " * 8, ["note " * 30], 0, 0, 0)
        text = Text.from_ansi(self.output.getvalue()).plain
        self.assertLessEqual(len(text.splitlines()), 8)
        self.assertTrue(all(cell_len(line) <= 20 for line in text.splitlines()))

    def test_small_settings_frame_keeps_status_visible(self) -> None:
        self.console.width = 40
        self.console.height = 10
        tui._render_settings("main", hover=6, status_msg="Import complete.", _frame_footer=5)
        text = Text.from_ansi(self.output.getvalue()).plain
        self.assertIn("▸ import database", text)
        self.assertIn("Import complete.", text)
        self.assertLessEqual(len(text.splitlines()), 10)

    def test_help_can_scroll_to_commands_below_the_viewport(self) -> None:
        self.console.width = 60
        self.console.height = 12
        scroll = tui._render_help_screen(_frame_scroll=1000)
        text = Text.from_ansi(self.output.getvalue()).plain
        self.assertGreater(scroll, 0)
        self.assertIn("Open settings preferences", text)
        self.assertIn("PgUp/PgDn:page", text)
        self.assertLessEqual(len(text.splitlines()), 12)

    def test_static_prompt_does_not_treat_resize_as_answer(self) -> None:
        keys = iter([terminal.KEY_RESIZE, "y"])
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(tui, "_render_message") as render,
        ):
            answer = tui._read_message([Text("Continue? [y/N]")])
        self.assertEqual(answer, "y")
        self.assertEqual(render.call_count, 2)

    def test_archived_list_confirmation_survives_resize(self) -> None:
        db.create_list("archived")
        db.archive_list("archived")
        keys = iter(["d", terminal.KEY_RESIZE, terminal.KEY_ESC, "q"])
        modes = []
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(tui, "_render_archived_lists", side_effect=lambda *args, **kwargs: modes.append(args[3])),
        ):
            tui._run_archived_lists_loop()
        self.assertEqual(modes, ["normal", "confirm", "confirm", "normal"])
        self.assertEqual(db.get_archived_lists()[0]["name"], "archived")

    def test_password_resize_preserves_masked_input(self) -> None:
        keys = iter(["a", terminal.KEY_RESIZE, "b", terminal.KEY_ENTER])
        output = io.StringIO()
        with (
            patch.object(terminal, "read_key", side_effect=lambda: next(keys)),
            patch.object(sys, "stdout", output),
        ):
            password = tui.prompt_password()
        self.assertEqual(password, "ab")
        self.assertIn("Enter password: *", output.getvalue())
        self.assertNotIn("ab", output.getvalue())


@unittest.skipIf(terminal.IS_WINDOWS, "Unix pseudo-terminal tests")
class TerminalInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.master, self.slave = pty.openpty()
        self.stack.callback(os.close, self.master)
        self.stack.callback(os.close, self.slave)
        stdin = self.stack.enter_context(os.fdopen(os.dup(self.slave), encoding="utf-8"))
        self.stack.enter_context(patch.object(sys, "stdin", stdin))
        self.stack.enter_context(patch.object(sys, "stdout", io.StringIO()))
        self.stack.enter_context(patch.object(terminal, "_last_size", None))
        termios.tcsetwinsize(self.slave, (24, 80))

    def test_waiting_for_input_reports_resize_without_a_key(self) -> None:
        with terminal.raw_mode():
            timer = threading.Timer(0.05, termios.tcsetwinsize, (self.slave, (10, 30)))
            rescue = threading.Timer(1, os.write, (self.master, b"x"))
            timer.start()
            rescue.start()
            try:
                start = time.monotonic()
                self.assertEqual(terminal.read_key(), terminal.KEY_RESIZE)
                self.assertLess(time.monotonic() - start, 1)
            finally:
                timer.join(timeout=1)
                rescue.cancel()
                rescue.join(timeout=1)

            termios.tcsetwinsize(self.slave, (40, 120))
            self.assertEqual(terminal.read_key(), terminal.KEY_RESIZE)
            os.write(self.master, b"x")
            self.assertEqual(terminal.read_key(), "x")

    def test_pasted_unicode_and_arrow_keys_do_not_get_stuck_in_buffer(self) -> None:
        with terminal.raw_mode():
            os.write(self.master, "abcé🙂\x1b[A\x1b[6~z".encode())
            expected = [*"abcé🙂", terminal.KEY_ARROW_UP, terminal.KEY_PAGE_DOWN, "z"]
            self.assertEqual([terminal.read_key() for _ in expected], expected)

    def test_escape_times_out_and_terminal_settings_are_restored(self) -> None:
        original = termios.tcgetattr(self.slave)
        with terminal.raw_mode():
            os.write(self.master, b"\x1b")
            self.assertEqual(terminal.read_key(), terminal.KEY_ESC)
        restored = termios.tcgetattr(self.slave)
        # macOS may set PENDIN while applying otherwise identical settings.
        restored[3] &= ~getattr(termios, "PENDIN", 0)
        original[3] &= ~getattr(termios, "PENDIN", 0)
        self.assertEqual(restored, original)

    def test_resize_during_a_utf8_character_preserves_pending_bytes(self) -> None:
        with terminal.raw_mode():
            os.write(self.master, b"\xc3")
            timer = threading.Timer(0.05, termios.tcsetwinsize, (self.slave, (10, 30)))
            rescue = threading.Timer(1, os.write, (self.master, b"\xa9"))
            timer.start()
            rescue.start()
            try:
                self.assertEqual(terminal.read_key(), terminal.KEY_RESIZE)
            finally:
                timer.join(timeout=1)
                rescue.cancel()
                rescue.join(timeout=1)
            os.write(self.master, b"\xa9")
            self.assertEqual(terminal.read_key(), "é")


@unittest.skipIf(terminal.IS_WINDOWS, "Unix pseudo-terminal tests")
class LiveTuiResizeTests(unittest.TestCase):
    def test_running_app_redraws_on_resize_without_keyboard_input(self) -> None:
        master, slave = pty.openpty()
        process = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                termios.tcsetwinsize(slave, (24, 80))
                environment = os.environ.copy()
                environment.update({
                    "TD_DB_PATH": str(Path(directory) / "td.db"),
                    "TD_CONFIG_PATH": str(Path(directory) / "config.toml"),
                    "TERM": "xterm-256color",
                    "NO_COLOR": "1",
                    # Exported shell dimensions must not pin the Rich console.
                    "COLUMNS": "80",
                    "LINES": "24",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                })
                process = subprocess.Popen(
                    [sys.executable, "-m", "td", "--list", "main"],
                    stdin=slave, stdout=slave, stderr=slave,
                    env=environment, start_new_session=True,
                )

                def read_frame():
                    deadline = time.monotonic() + 5
                    data = b""
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.1)[0]:
                            data += os.read(master, 65536)
                            if b"\x1b[J" in data:
                                frame = data.rsplit(b"\x1b[J", 1)[0].rsplit(b"\x1b[H", 1)[-1]
                                return Text.from_ansi(frame.decode().replace("\r\n", "\n")).plain
                    self.fail(f"TUI did not redraw: {data!r}")

                self.assertIn("td • main", read_frame())
                for width, height in [(22, 8), (100, 35), (40, 12)]:
                    with self.subTest(width=width, height=height):
                        termios.tcsetwinsize(slave, (height, width))
                        frame = read_frame()
                        self.assertIn("td • main", frame)
                        self.assertLessEqual(len(frame.splitlines()), height)
                        self.assertTrue(all(cell_len(line) <= width for line in frame.splitlines()))

                os.write(master, b"q")
                deadline = time.monotonic() + 5
                remaining = b""
                while process.poll() is None and time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        remaining += os.read(master, 65536)
                self.assertEqual(process.poll(), 0, remaining.decode(errors="replace"))
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
